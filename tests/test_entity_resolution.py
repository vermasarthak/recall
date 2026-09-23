"""Tests for entity resolution, alias matching, and Jaro-Winkler fuzzy matching."""

from recall.config import TestClock
from recall.db.store import StorageEngine
from recall.engine.extractor import jaro_winkler_similarity
from recall.engine.ingest import EntityResolver
from recall.models.entity import EntityCreate, EntityType


def test_jaro_winkler_similarity_values():
    assert jaro_winkler_similarity("Sarthak", "Sarthak") == 1.0
    assert jaro_winkler_similarity("Google", "Goog") > 0.85
    assert jaro_winkler_similarity("Apple", "Microsoft") < 0.5


def test_entity_resolver_hierarchy(tmp_path):
    clock = TestClock()
    store = StorageEngine(str(tmp_path / "test.db"), clock=clock)
    resolver = EntityResolver(store, similarity_threshold=0.85, ambiguity_margin=0.05)

    # 1. Create Entity with alias
    e1 = store.create_entity(
        EntityCreate(type=EntityType.PERSON, canonical_name="Sarthak Verma", aliases=["Sarthak", "SV"])
    )

    # Resolve exact canonical name
    res1, amb1 = resolver.resolve("Sarthak Verma")
    assert res1.id == e1.id
    assert not amb1

    # Resolve exact alias
    res2, amb2 = resolver.resolve("sarthak")
    assert res2.id == e1.id
    assert not amb2

    # Resolve fuzzy match
    res3, amb3 = resolver.resolve("Sarthak Verm")
    assert res3.id == e1.id
    assert not amb3


def test_entity_resolver_ambiguity_detection(tmp_path):
    clock = TestClock()
    store = StorageEngine(str(tmp_path / "test.db"), clock=clock)
    resolver = EntityResolver(store, similarity_threshold=0.80, ambiguity_margin=0.10)

    # Create two very similar entities
    e1 = store.create_entity(EntityCreate(type=EntityType.PERSON, canonical_name="John Smith"))
    e2 = store.create_entity(EntityCreate(type=EntityType.PERSON, canonical_name="Jon Smith"))

    # Resolve "John Smit" -> matches both closely
    res, is_ambiguous = resolver.resolve("John Smit")
    assert is_ambiguous
