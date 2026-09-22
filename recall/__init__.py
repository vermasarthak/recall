"""Recall: Temporal Entity Memory Engine for Social AI."""

from recall.client import Recall
from recall.config import Clock, SystemClock, TestClock
from recall.models.entity import EntityType, EntityCreate, EntityRecord
from recall.models.fact import FactCreate, FactRecord, SourceType, PredicatePolicy
from recall.models.query import QueryResult, SalienceBreakdown

__version__ = "0.1.0"
__all__ = [
    "Recall",
    "Clock",
    "SystemClock",
    "TestClock",
    "EntityType",
    "EntityCreate",
    "EntityRecord",
    "FactCreate",
    "FactRecord",
    "SourceType",
    "PredicatePolicy",
    "QueryResult",
    "SalienceBreakdown",
]
