"""Entity domain models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from recall.config import ensure_utc


class EntityType(str, Enum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    EVENT = "event"
    CONCEPT = "concept"


class EntityCreate(BaseModel):
    id: str | None = None
    type: EntityType
    canonical_name: str = Field(..., min_length=1)
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("canonical_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Canonical name cannot be empty or whitespace.")
        return s


class EntityRecord(BaseModel):
    id: str
    type: EntityType
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_dt(cls, v: datetime) -> datetime:
        return ensure_utc(v)
