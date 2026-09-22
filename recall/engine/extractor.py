"""Entity resolution, Jaro-Winkler fuzzy matching, and extraction provider interfaces."""

from abc import ABC, abstractmethod
from datetime import datetime
import json
import os
import re

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from recall.config import Clock, ensure_utc
from recall.models.entity import EntityCreate, EntityRecord, EntityType
from recall.models.fact import FactCreate, SourceType


def jaro_winkler_similarity(s1: str, s2: str, p: float = 0.1) -> float:
    """Computes Jaro-Winkler similarity between two strings in range [0.0, 1.0]."""
    s1, s2 = s1.lower().strip(), s2.lower().strip()
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2

    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    transpositions //= 2
    jaro = (matches / len1 + matches / len2 + (matches - transpositions) / matches) / 3.0

    # Prefix scale
    prefix = 0
    for i in range(min(4, len1, len2)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + prefix * p * (1.0 - jaro)


class ExtractedEntityCandidate(BaseModel):
    temp_id: str
    type: EntityType
    canonical_name: str
    aliases: List[str] = Field(default_factory=list)


class ExtractedFactCandidate(BaseModel):
    subject_ref: str  # temp_id or name
    predicate: str
    object_value: Any
    confidence: float = 1.0
    source_type: SourceType = SourceType.DIRECT_STATEMENT
    valid_from: Optional[datetime] = None


class ExtractedTurn(BaseModel):
    entities: List[ExtractedEntityCandidate] = Field(default_factory=list)
    facts: List[ExtractedFactCandidate] = Field(default_factory=list)


class BaseExtractor(ABC):
    """Abstract interface for conversational turn extraction."""

    @abstractmethod
    def extract(self, speaker: str, text: str, event_time: datetime) -> ExtractedTurn:
        pass


class FixtureExtractor(BaseExtractor):
    """Deterministic fixture extractor for offline testing and WhatsApp timeline demo."""

    def __init__(self):
        self._rules = [
            # Pattern: "John started working at Amazon"
            (r"(\w+)\s+(?:started working at|joined)\s+(\w+)", "primary_employer", EntityType.ORGANIZATION),
            # Pattern: "John works at Google"
            (r"(\w+)\s+works at\s+(\w+)", "primary_employer", EntityType.ORGANIZATION),
            # Pattern: "John lives in Bangalore" / "moved to Chennai"
            (r"(\w+)\s+(?:lives in|moved to)\s+(\w+)", "residence", EntityType.LOCATION),
            # Pattern: "John speaks Spanish"
            (r"(\w+)\s+speaks\s+(\w+)", "speaks_language", EntityType.CONCEPT),
            # Pattern: "John likes coffee"
            (r"(\w+)\s+likes\s+(\w+)", "likes", EntityType.CONCEPT),
        ]

    def extract(self, speaker: str, text: str, event_time: datetime) -> ExtractedTurn:
        ev_time = ensure_utc(event_time)
        entities: Dict[str, ExtractedEntityCandidate] = {}
        facts: List[ExtractedFactCandidate] = []

        # Add speaker entity
        speaker_name = speaker.capitalize()
        entities[speaker_name] = ExtractedEntityCandidate(
            temp_id=f"temp_{speaker_name.lower()}",
            type=EntityType.PERSON,
            canonical_name=speaker_name,
            aliases=[speaker]
        )

        for pattern, predicate, obj_type in self._rules:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                subj_name = match.group(1).capitalize()
                obj_name = match.group(2).capitalize()

                if subj_name not in entities:
                    entities[subj_name] = ExtractedEntityCandidate(
                        temp_id=f"temp_{subj_name.lower()}",
                        type=EntityType.PERSON,
                        canonical_name=subj_name
                    )

                obj_temp_id = f"temp_{obj_name.lower()}"
                if obj_name not in entities:
                    entities[obj_name] = ExtractedEntityCandidate(
                        temp_id=obj_temp_id,
                        type=obj_type,
                        canonical_name=obj_name
                    )

                facts.append(
                    ExtractedFactCandidate(
                        subject_ref=entities[subj_name].temp_id,
                        predicate=predicate,
                        object_value=obj_name,
                        confidence=0.95,
                        source_type=SourceType.DIRECT_STATEMENT,
                        valid_from=ev_time
                    )
                )

        return ExtractedTurn(entities=list(entities.values()), facts=facts)


class OpenAIProviderAdapter(BaseExtractor):
    """Structured extraction adapter for OpenAI/OpenRouter compatible endpoints."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str = "https://api.openai.com/v1", timeout_sec: float = 10.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    def extract(self, speaker: str, text: str, event_time: datetime) -> ExtractedTurn:
        import urllib.request
        ev_time = ensure_utc(event_time)

        prompt = (
            f"Extract entities and facts from speaker '{speaker}': \"{text}\". "
            "Return JSON matching keys 'entities' and 'facts'."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a structured fact extraction assistant. Output JSON only."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"}
        }

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return ExtractedTurn.model_validate(parsed)
        except Exception as e:
            raise RuntimeError(f"OpenAIProviderAdapter extraction failed: {e}")
