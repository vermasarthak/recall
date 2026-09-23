"""Tests for bitemporal storage, versioning rules, and SQL persistence."""

from datetime import UTC, datetime

import pytest

from recall.config import TestClock
from recall.db.store import StorageEngine, calculate_fact_hash, canonical_json_dumps
from recall.models.entity import EntityCreate, EntityType
from recall.models.fact import FactRecord, SourceType


def test_canonical_json_type_distinction():
    assert canonical_json_dumps({"a": 1}) != canonical_json_dumps({"a": "1"})
    assert calculate_fact_hash("ent1", "val", 1) != calculate_fact_hash("ent1", "val", "1")


def test_naive_datetime_rejection(tmp_path):
    clock = TestClock()
    store = StorageEngine(str(tmp_path / "test.db"), clock=clock)

    naive_dt = datetime(2026, 1, 1, 0, 0, 0)
    with pytest.raises(ValueError):
        store.query_facts(valid_at=naive_dt)


def test_bitemporal_half_open_intervals(tmp_path):
    clock = TestClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
    store = StorageEngine(str(tmp_path / "test.db"), clock=clock)

    # Insert entity
    ent = store.create_entity(EntityCreate(type=EntityType.PERSON, canonical_name="John"))

    # Insert Fact 1: John worked at Google from Jan 1 to July 1, 2026
    v_from = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    v_to = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
    tx_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

    fact1 = FactRecord(
        version_id="ver_1",
        logical_id="log_1",
        subject_id=ent.id,
        predicate="primary_employer",
        object_value="Google",
        confidence=1.0,
        source_type=SourceType.DIRECT_STATEMENT,
        source_ref="msg_1",
        valid_from=v_from,
        valid_to=v_to,
        tx_from=tx_time,
        tx_to=None,
        fact_hash=calculate_fact_hash(ent.id, "primary_employer", "Google"),
    )
    store.insert_fact_version(fact1)

    # Query March 1, 2026 (inside interval) -> should return Google
    march_1 = datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)
    res_march = store.query_facts(subject_id=ent.id, valid_at=march_1, known_at=tx_time)
    assert len(res_march) == 1
    assert res_march[0].object_value == "Google"

    # Query July 1, 2026 (exact upper boundary [valid_from, valid_to)) -> should return empty (half-open)
    july_1 = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
    res_july = store.query_facts(subject_id=ent.id, valid_at=july_1, known_at=tx_time)
    assert len(res_july) == 0


def test_knowledge_time_versioning_and_historical_correction(tmp_path):
    # At T1 (Jan 1), learn John at Google starting Jan 1
    t1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    clock = TestClock(t1)
    store = StorageEngine(str(tmp_path / "test.db"), clock=clock)

    ent = store.create_entity(EntityCreate(type=EntityType.PERSON, canonical_name="John"))

    ver1 = FactRecord(
        version_id="ver_1",
        logical_id="log_1",
        subject_id=ent.id,
        predicate="primary_employer",
        object_value="Google",
        confidence=1.0,
        source_type=SourceType.DIRECT_STATEMENT,
        source_ref="msg_1",
        valid_from=t1,
        valid_to=None,
        tx_from=t1,
        tx_to=None,
        fact_hash=calculate_fact_hash(ent.id, "primary_employer", "Google"),
    )
    store.insert_fact_version(ver1)

    # At T2 (July 1), learn John switched to Amazon on July 1
    t2 = datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC)
    clock.set(t2)

    # Revision: Close ver1 tx_to at t2
    store.close_fact_tx_to("ver_1", tx_to=t2)

    # Insert revised historical version of Google valid [Jan 1, July 1) known_at t2
    ver1_revised = FactRecord(
        version_id="ver_1_revised",
        logical_id="log_1",
        subject_id=ent.id,
        predicate="primary_employer",
        object_value="Google",
        confidence=1.0,
        source_type=SourceType.DIRECT_STATEMENT,
        source_ref="msg_1",
        valid_from=t1,
        valid_to=t2,
        tx_from=t2,
        tx_to=None,
        fact_hash=ver1.fact_hash,
    )
    store.insert_fact_version(ver1_revised)

    # Insert Amazon version valid [July 1, NULL) known_at t2
    ver2 = FactRecord(
        version_id="ver_2",
        logical_id="log_2",
        subject_id=ent.id,
        predicate="primary_employer",
        object_value="Amazon",
        confidence=1.0,
        source_type=SourceType.DIRECT_STATEMENT,
        source_ref="msg_2",
        valid_from=t2,
        valid_to=None,
        tx_from=t2,
        tx_to=None,
        fact_hash=calculate_fact_hash(ent.id, "primary_employer", "Amazon"),
    )
    store.insert_fact_version(ver2)

    # 1. Query as known at T1 (before T2) for August -> sees Google [Jan 1, NULL)
    august = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
    res_t1 = store.query_facts(subject_id=ent.id, valid_at=august, known_at=t1)
    assert len(res_t1) == 1
    assert res_t1[0].object_value == "Google"

    # 2. Query as known at T2 for August -> sees Amazon
    res_t2_aug = store.query_facts(subject_id=ent.id, valid_at=august, known_at=t2)
    assert len(res_t2_aug) == 1
    assert res_t2_aug[0].object_value == "Amazon"

    # 3. Query as known at T2 for March (historical valid time) -> sees Google
    march = datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)
    res_t2_mar = store.query_facts(subject_id=ent.id, valid_at=march, known_at=t2)
    assert len(res_t2_mar) == 1
    assert res_t2_mar[0].object_value == "Google"


def test_repeated_tx_to_closure_forbidden(tmp_path):
    clock = TestClock()
    store = StorageEngine(str(tmp_path / "test.db"), clock=clock)
    ent = store.create_entity(EntityCreate(type=EntityType.PERSON, canonical_name="Alice"))

    ver1 = FactRecord(
        version_id="ver_1",
        logical_id="log_1",
        subject_id=ent.id,
        predicate="residence",
        object_value="Chennai",
        confidence=1.0,
        source_type=SourceType.DIRECT_STATEMENT,
        source_ref="msg_1",
        valid_from=clock.now(),
        tx_from=clock.now(),
        fact_hash=calculate_fact_hash(ent.id, "residence", "Chennai"),
    )
    store.insert_fact_version(ver1)

    now2 = clock.now()
    store.close_fact_tx_to("ver_1", tx_to=now2)

    with pytest.raises(ValueError, match="Repeated closure forbidden"):
        store.close_fact_tx_to("ver_1", tx_to=now2)
