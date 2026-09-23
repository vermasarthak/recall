"""Recall core engine package."""

from recall.engine.conflict import ConflictResolver, get_predicate_policy
from recall.engine.decay import SalienceScorer, calculate_lexical_similarity, calculate_retention
from recall.engine.extractor import BaseExtractor, FixtureExtractor, OpenAIProviderAdapter, jaro_winkler_similarity
from recall.engine.ingest import EntityResolver, IngestionPipeline

__all__ = [
    "BaseExtractor",
    "ConflictResolver",
    "EntityResolver",
    "FixtureExtractor",
    "IngestionPipeline",
    "OpenAIProviderAdapter",
    "SalienceScorer",
    "calculate_lexical_similarity",
    "calculate_retention",
    "get_predicate_policy",
    "jaro_winkler_similarity",
]
