"""Fact and Relation domain models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from recall.config import ensure_utc


class SourceType(str, Enum):
    DIRECT_STATEMENT = "direct_statement"
    INFERENCE = "inference"
    HEARSAY = "hearsay"
    USER_EDIT = "user_edit"


class PredicatePolicy(str, Enum):
    SINGLE_VALUED = "single_valued"
    MULTI_VALUED = "multi_valued"
    RETRACTION = "retraction"


class FactCreate(BaseModel):
    subject: str = Field(..., min_length=1, description="Entity ID or canonical name")
    predicate: str = Field(..., min_length=1)
    object_value: Any = Field(...)
    object_entity_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_type: SourceType = SourceType.DIRECT_STATEMENT
    source_ref: str = Field(..., min_length=1, description="Message UUID or source reference")
    valid_from: datetime | None = None

    @field_validator("valid_from")
    @classmethod
    def validate_valid_from(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            return ensure_utc(v)
        return None


class FactRecord(BaseModel):
    version_id: str
    logical_id: str
    subject_id: str
    predicate: str
    object_value: Any
    object_entity_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    source_type: SourceType
    source_ref: str
    valid_from: datetime
    valid_to: datetime | None = None
    tx_from: datetime
    tx_to: datetime | None = None
    fact_hash: str

    @field_validator("valid_from", "tx_from")
    @classmethod
    def validate_req_dt(cls, v: datetime) -> datetime:
        return ensure_utc(v)

    @field_validator("valid_to", "tx_to")
    @classmethod
    def validate_opt_dt(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            return ensure_utc(v)
        return None


class RelationCreate(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    source_ref: str
    valid_from: datetime | None = None

    @field_validator("valid_from")
    @classmethod
    def validate_vf(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            return ensure_utc(v)
        return None


class RelationRecord(BaseModel):
    version_id: str
    logical_id: str
    source_id: str
    target_id: str
    relation_type: str
    strength: float = Field(ge=0.0, le=1.0)
    source_ref: str
    valid_from: datetime
    valid_to: datetime | None = None
    tx_from: datetime
    tx_to: datetime | None = None

    @field_validator("valid_from", "tx_from")
    @classmethod
    def validate_req_dt(cls, v: datetime) -> datetime:
        return ensure_utc(v)

    @field_validator("valid_to", "tx_to")
    @classmethod
    def validate_opt_dt(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            return ensure_utc(v)
        return None
