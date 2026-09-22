"""Tests for public Recall client API, context manager, and end-to-end workflows."""

from datetime import datetime, timezone, timedelta
import pytest
from recall.client import Recall
from recall.config import TestClock
from recall.models.entity import EntityType
from recall.models.fact import FactCreate, SourceType


def test_end_to_end_client_workflow(tmp_path):
    db_file = str(tmp_path / "recall_test.db")
    start_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    clock = TestClock(start_time)

    with Recall(db_path=db_file, clock=clock) as client:
        # 1. Ingest turn 1 (Jan 1, 2026): John works at Google
        res1 = client.ingest_turn(
            speaker="User",
            text="John works at Google",
            conversation_id="conv_1",
            message_id="msg_1",
            timestamp=start_time
        )
        assert len(res1.inserted_facts) == 1
        assert res1.inserted_facts[0].object_value == "Google"

        # Query Jan 1 -> sees Google
        q1 = client.query("John", context="employment", valid_at=start_time)
        assert len(q1) == 1
        assert q1[0].fact.object_value == "Google"

        # 2. Advance clock to July 1, 2026: John started working at Amazon
        july_1 = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)
        clock.set(july_1)

        res2 = client.ingest_turn(
            speaker="User",
            text="John started working at Amazon",
            conversation_id="conv_2",
            message_id="msg_2",
            timestamp=july_1
        )
        assert len(res2.inserted_facts) == 1
        assert res2.inserted_facts[0].object_value == "Amazon"

        # Query July 1 -> sees Amazon
        q2 = client.query("John", context="employment", valid_at=july_1)
        assert len(q2) == 1
        assert q2[0].fact.object_value == "Amazon"

        # Historical query Jan 1 (known July 1) -> sees Google
        q_hist = client.query("John", context="employment", valid_at=start_time, known_at=july_1)
        assert len(q_hist) == 1
        assert q_hist[0].fact.object_value == "Google"

        # 3. Explicit correction
        amazon_logical_id = res2.inserted_facts[0].logical_id
        corr = client.correct_fact(
            logical_id=amazon_logical_id,
            new_object_value="AWS",
            source_ref="user_correction"
        )
        assert corr.object_value == "AWS"

        # Query July 1 -> sees AWS
        q3 = client.query("John", context="employment", valid_at=july_1)
        assert len(q3) == 1
        assert q3[0].fact.object_value == "AWS"

    # Reopen client to verify persistence
    with Recall(db_path=db_file, clock=clock) as client_reopened:
        q_persist = client_reopened.query("John", context="employment", valid_at=july_1)
        assert len(q_persist) == 1
        assert q_persist[0].fact.object_value == "AWS"

def test_global_semantic_search():
    from recall.client import Recall
    from recall.engine.similarity import SimilarityProvider
    
    # Simple mock similarity that returns 0.9 if words overlap
    class MockSim(SimilarityProvider):
        def calculate_similarity(self, text_a: str, text_b: str) -> float:
            words_a = set(text_a.lower().split())
            words_b = set(text_b.lower().split())
            if words_a & words_b:
                return 0.9
            return 0.1
            
    client = Recall(db_path=":memory:", similarity_provider=MockSim())
    client.ingest_turn("John", "John likes StarWars", "c1")
    client.ingest_turn("Alice", "Alice likes cookies", "c1")
    
    # Now semantic search without knowing the entity!
    results = client.search(query="watching StarWars movies", min_score=0.7)
    assert len(results) == 1
    assert "Starwars" in results[0].fact.object_value
    assert results[0].subject_entity.canonical_name == "John"
