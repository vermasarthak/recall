"""Tests for conflict resolution, source precedence, and predicate policies."""

from datetime import datetime, timezone
import pytest
from recall.config import TestClock
from recall.db.store import StorageEngine
from recall.engine.conflict import ConflictResolver, get_predicate_policy
from recall.models.entity import EntityCreate, EntityType
from recall.models.fact import FactCreate, PredicatePolicy, SourceType

def test_predicate_policy_detection():
    assert get_predicate_policy("primary_employer") == PredicatePolicy.SINGLE_VALUED
    assert get_predicate_policy("residence") == PredicatePolicy.SINGLE_VALUED
    assert get_predicate_policy("speaks_language") == PredicatePolicy.MULTI_VALUED
    assert get_predicate_policy("likes") == PredicatePolicy.MULTI_VALUED
    assert get_predicate_policy("retract_employer") == PredicatePolicy.RETRACTION

def test_multi_valued_coexistence(tmp_path):
    clock = TestClock()
    store = StorageEngine(str(tmp_path / "test.db"), clock=clock)
    resolver = ConflictResolver(store, clock)

    ent = store.create_entity(EntityCreate(type=EntityType.PERSON, canonical_name="John"))

    f1 = FactCreate(
        subject=ent.id,
        predicate="speaks_language",
        object_value="English",
        source_type=SourceType.DIRECT_STATEMENT,
        source_ref="msg_1"
    )
    rec1, _, unres1 = resolver.resolve_and_apply_fact(f1, subject_id=ent.id)
    assert rec1 is not None
    assert len(unres1) == 0

    f2 = FactCreate(
        subject=ent.id,
        predicate="speaks_language",
        object_value="Spanish",
        source_type=SourceType.DIRECT_STATEMENT,
        source_ref="msg_2"
    )
    rec2, _, unres2 = resolver.resolve_and_apply_fact(f2, subject_id=ent.id)
    assert rec2 is not None
    assert len(unres2) == 0

    # Query active facts -> both English and Spanish exist simultaneously
    active = store.query_facts(subject_id=ent.id, predicate="speaks_language")
    assert len(active) == 2
    objs = {r.object_value for r in active}
    assert objs == {"English", "Spanish"}


def test_single_valued_conflict_resolution(tmp_path):
    t1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    clock = TestClock(t1)
    store = StorageEngine(str(tmp_path / "test.db"), clock=clock)
    resolver = ConflictResolver(store, clock)

    ent = store.create_entity(EntityCreate(type=EntityType.PERSON, canonical_name="John"))

    # 1. Direct statement: John works at Google
    f1 = FactCreate(
        subject=ent.id,
        predicate="primary_employer",
        object_value="Google",
        source_type=SourceType.DIRECT_STATEMENT,
        source_ref="msg_1",
        valid_from=t1
    )
    rec1, _, _ = resolver.resolve_and_apply_fact(f1, subject_id=ent.id, now=t1)
    assert rec1.object_value == "Google"

    # 2. At T2 (July 1), Direct statement: John works at Amazon
    t2 = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
    clock.set(t2)
    f2 = FactCreate(
        subject=ent.id,
        predicate="primary_employer",
        object_value="Amazon",
        source_type=SourceType.DIRECT_STATEMENT,
        source_ref="msg_2",
        valid_from=t2
    )
    rec2, _, _ = resolver.resolve_and_apply_fact(f2, subject_id=ent.id, now=t2)
    assert rec2.object_value == "Amazon"

    # Query active facts at T2 -> only Amazon active
    active = store.query_facts(subject_id=ent.id, predicate="primary_employer", valid_at=t2, known_at=t2)
    assert len(active) == 1
    assert active[0].object_value == "Amazon"

    # Inspect history -> Google version closed valid_to at T2, Amazon open
    hist = store.query_history(rec1.logical_id)
    assert len(hist) >= 1
    assert hist[-1].valid_to == t2


def test_source_precedence_rejection(tmp_path):
    clock = TestClock()
    store = StorageEngine(str(tmp_path / "test.db"), clock=clock)
    resolver = ConflictResolver(store, clock)

    ent = store.create_entity(EntityCreate(type=EntityType.PERSON, canonical_name="John"))

    # High precedence: DIRECT_STATEMENT
    f_high = FactCreate(
        subject=ent.id,
        predicate="primary_employer",
        object_value="Google",
        source_type=SourceType.DIRECT_STATEMENT,
        source_ref="msg_1"
    )
    rec_high, _, _ = resolver.resolve_and_apply_fact(f_high, subject_id=ent.id)
    assert rec_high is not None

    # Low precedence: INFERENCE trying to overwrite Google with Apple
    f_low = FactCreate(
        subject=ent.id,
        predicate="primary_employer",
        object_value="Apple",
        source_type=SourceType.INFERENCE,
        source_ref="msg_2"
    )
    rec_low, _, unres = resolver.resolve_and_apply_fact(f_low, subject_id=ent.id)
    assert rec_low is None
    assert len(unres) == 1
    assert unres[0]["reason"] == "lower_precedence_or_confidence"

    # Active remains Google
    active = store.query_facts(subject_id=ent.id, predicate="primary_employer")
    assert len(active) == 1
    assert active[0].object_value == "Google"
