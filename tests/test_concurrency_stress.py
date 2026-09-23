"""Concurrent in-process stress tests for Recall bitemporal store."""

import concurrent.futures
from datetime import UTC, datetime

from recall.config import TestClock
from recall.db.store import StorageEngine, calculate_fact_hash
from recall.models.entity import EntityCreate, EntityType
from recall.models.fact import FactRecord, SourceType


def test_concurrent_tenant_writes(tmp_path):
    """Verify concurrent writes across threads into tenant SQLite storage engine."""
    clock = TestClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))
    db_path = str(tmp_path / "concurrent_test.db")
    store = StorageEngine(db_path, clock=clock)

    # Pre-create entities
    for i in range(5):
        store.create_entity(EntityCreate(id=f"user_{i}", canonical_name=f"User_{i}", type=EntityType.PERSON))

    def write_fact(i: int):
        subject_id = f"user_{i % 5}"
        v_from = datetime(2026, 1, 1 + (i % 25), 12, 0, tzinfo=UTC)
        fact = FactRecord(
            version_id=f"ver_{i}",
            logical_id=f"log_{i}",
            subject_id=subject_id,
            predicate="location",
            object_value=f"City_{i}",
            confidence=1.0,
            source_type=SourceType.DIRECT_STATEMENT,
            source_ref=f"msg_{i}",
            valid_from=v_from,
            valid_to=None,
            tx_from=v_from,
            tx_to=None,
            fact_hash=calculate_fact_hash(subject_id, "location", f"City_{i}"),
        )
        return store.insert_fact_version(fact)

    num_threads = 8
    num_writes_per_thread = 10
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(write_fact, i) for i in range(num_threads * num_writes_per_thread)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == num_threads * num_writes_per_thread

    # Verify facts were persisted
    facts = store.query_facts(
        subject_id="user_0",
        valid_at=datetime(2026, 6, 1, tzinfo=UTC),
        known_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    assert len(facts) >= 1
