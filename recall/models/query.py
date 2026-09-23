"""Query and Ingestion response domain models."""

from typing import Any

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
    object_entity: EntityRecord | None = None
    is_unresolved: bool = False


class IngestionResult(BaseModel):
    inserted_facts: list[FactRecord] = Field(default_factory=list)
    versioned_facts: list[FactRecord] = Field(default_factory=list)
    reinforced_facts: list[str] = Field(default_factory=list)
    inserted_relations: list[RelationRecord] = Field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_conflicts: list[dict[str, Any]] = Field(default_factory=list)
