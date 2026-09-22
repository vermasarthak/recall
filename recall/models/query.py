"""Query and Ingestion response domain models."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from recall.models.entity import EntityRecord
from recall.models.fact import FactRecord, RelationRecord


class SalienceBreakdown(BaseModel):
    similarity: float = Field(ge=0.0, le=1.0)
    retention: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    composite_score: float = Field(ge=0.0, le=1.0)


class QueryResult(BaseModel):
    fact: FactRecord
    salience: SalienceBreakdown
    subject_entity: EntityRecord
    object_entity: Optional[EntityRecord] = None
    is_unresolved: bool = False


class IngestionResult(BaseModel):
    inserted_facts: List[FactRecord] = Field(default_factory=list)
    versioned_facts: List[FactRecord] = Field(default_factory=list)
    reinforced_facts: List[str] = Field(default_factory=list)
    inserted_relations: List[RelationRecord] = Field(default_factory=list)
    rejected_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    unresolved_conflicts: List[Dict[str, Any]] = Field(default_factory=list)
