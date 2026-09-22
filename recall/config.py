"""Configuration, clock abstractions, and UTC temporal utilities for Recall."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import re
from typing import Optional


class NaiveDatetimeError(ValueError):
    """Raised when a naive datetime (lacking timezone information) is passed."""


def ensure_utc(dt: datetime) -> datetime:
    """Validates that a datetime is timezone-aware and normalizes it to UTC.
    
    Raises:
        NaiveDatetimeError: If dt has no tzinfo.
    """
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise NaiveDatetimeError(f"Naive datetime provided: {dt}. Datetimes must be timezone-aware (e.g., UTC).")
    return dt.astimezone(timezone.utc)


def to_iso_utc(dt: datetime) -> str:
    """Formats a timezone-aware datetime as a canonical ISO 8601 UTC string."""
    utc_dt = ensure_utc(dt)
    return utc_dt.isoformat()


def parse_iso_utc(dt_str: str) -> datetime:
    """Parses a stored ISO 8601 UTC datetime string into a timezone-aware datetime."""
    dt = datetime.fromisoformat(dt_str)
    return ensure_utc(dt)


class Clock(ABC):
    """Abstract injectable clock interface for deterministic time management."""

    @abstractmethod
    def now(self) -> datetime:
        """Returns the current timezone-aware UTC datetime."""
        pass


class SystemClock(Clock):
    """System clock returning actual UTC current time."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class TestClock(Clock):
    """In-memory test clock for simulated time travel and deterministic testing."""

    __test__ = False

    def __init__(self, initial_time: Optional[datetime] = None):
        if initial_time is not None:
            self._current_time = ensure_utc(initial_time)
        else:
            self._current_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._current_time

    def set(self, dt: datetime) -> None:
        self._current_time = ensure_utc(dt)

    def advance(self, days: float = 0, hours: float = 0, minutes: float = 0, seconds: float = 0) -> None:
        from datetime import timedelta
        delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        self._current_time += delta
