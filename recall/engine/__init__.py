"""Recall core engine package."""

from recall.engine.conflict import ConflictResolver, get_predicate_policy
from recall.engine.decay import SalienceScorer, calculate_retention, calculate_lexical_similarity
from recall.engine.extractor import BaseExtractor, FixtureExtractor, OpenAIProviderAdapter, jaro_winkler_similarity
from recall.engine.ingest import IngestionPipeline, EntityResolver

__all__ = [
    "ConflictResolver",
    "get_predicate_policy",
    "SalienceScorer",
    "calculate_retention",
    "calculate_lexical_similarity",
    "BaseExtractor",
    "FixtureExtractor",
    "OpenAIProviderAdapter",
    "jaro_winkler_similarity",
    "IngestionPipeline",
    "EntityResolver",
]
