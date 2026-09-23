"""Ingestion pipeline executing entity resolution, validation, and atomic storage."""

import uuid
from datetime import datetime

from recall.config import Clock, ensure_utc, to_iso_utc
from recall.db.store import StorageEngine
from recall.engine.conflict import ConflictResolver
from recall.engine.extractor import (
    ExtractedTurn,
    jaro_winkler_similarity,
)
from recall.models.entity import EntityCreate, EntityRecord, EntityType
from recall.models.fact import FactCreate
from recall.models.query import IngestionResult


class EntityResolver:
    """Resolves entity references against existing database entities."""

    def __init__(self, store: StorageEngine, similarity_threshold: float = 0.85, ambiguity_margin: float = 0.05):
        self.store = store
        self.threshold = similarity_threshold
        self.margin = ambiguity_margin

    def resolve(
        self, name_or_alias: str, default_type: EntityType = EntityType.PERSON, now: datetime | None = None
    ) -> tuple[EntityRecord, bool]:
        """Resolves a candidate entity name or alias.

        Returns:
            (EntityRecord, is_ambiguous)
        """
        clean_name = name_or_alias.strip()
        if not clean_name:
            raise ValueError("Entity reference name cannot be empty.")

        # 1. Exact canonical name match
        match = self.store.get_entity_by_canonical_name(clean_name)
        if match:
            return (match, False)

        # 2. Exact alias match
        all_entities = self.store.get_all_entities()
        clean_lower = clean_name.lower()
        for ent in all_entities:
            if any(alias.lower() == clean_lower for alias in ent.aliases):
                return (ent, False)

        # 3. Fuzzy Jaro-Winkler match
        candidates: list[tuple[EntityRecord, float]] = []
        for ent in all_entities:
            score = jaro_winkler_similarity(clean_name, ent.canonical_name)
            for alias in ent.aliases:
                score = max(score, jaro_winkler_similarity(clean_name, alias))
            if score >= self.threshold:
                candidates.append((ent, score))

        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_ent, best_score = candidates[0]

            # Ambiguity Check: if second candidate is within margin
            if len(candidates) > 1:
                second_ent, second_score = candidates[1]
                if (best_score - second_score) <= self.margin:
                    # Ambiguous! Return best entity but set is_ambiguous=True
                    return (best_ent, True)

            return (best_ent, False)

        # 4. Create new entity
        new_ent = self.store.create_entity(
            EntityCreate(type=default_type, canonical_name=clean_name.capitalize(), aliases=[clean_name]), now=now
        )
        return (new_ent, False)


class IngestionPipeline:
    """Atomic ingestion pipeline managing extraction, resolution, and versioning."""

    def __init__(self, store: StorageEngine, clock: Clock):
        self.store = store
        self.clock = clock
        self.resolver = EntityResolver(store)
        self.conflict_resolver = ConflictResolver(store, clock)

    def ingest_structured_turn(
        self,
        turn: ExtractedTurn,
        conv_id: str,
        message_id: str | None = None,
        speaker: str | None = None,
        event_time: datetime | None = None,
        now: datetime | None = None,
    ) -> IngestionResult:
        """Process structured extraction turn into atomic versioned database writes."""
        tx_now = ensure_utc(now or self.clock.now())
        ev_time = ensure_utc(event_time or tx_now)
        source_ref = message_id or f"msg_{uuid.uuid4().hex[:12]}"

        # Save source record
        conn = self.store.get_connection()
        with conn:
            conn.execute(
                """INSERT OR IGNORE INTO sources (id, message_id, speaker, raw_text, conv_id, event_time, tx_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?);""",
                (
                    f"src_{uuid.uuid4().hex[:12]}",
                    source_ref,
                    speaker,
                    "",
                    conv_id,
                    to_iso_utc(ev_time),
                    to_iso_utc(tx_now),
                ),
            )

        # Resolve temp_ids to DB EntityRecords
        temp_id_map: dict[str, EntityRecord] = {}

        for cand_ent in turn.entities:
            resolved_ent, is_amb = self.resolver.resolve(
                cand_ent.canonical_name, default_type=cand_ent.type, now=tx_now
            )
            temp_id_map[cand_ent.temp_id] = resolved_ent
            temp_id_map[cand_ent.canonical_name.lower()] = resolved_ent

        result = IngestionResult()

        for cand_fact in turn.facts:
            # Resolve subject entity
            subj_ref = cand_fact.subject_ref.lower()
            if subj_ref in temp_id_map:
                subj_ent = temp_id_map[subj_ref]
            else:
                subj_ent, _ = self.resolver.resolve(cand_fact.subject_ref, default_type=EntityType.PERSON, now=tx_now)

            fact_create = FactCreate(
                subject=subj_ent.id,
                predicate=cand_fact.predicate,
                object_value=cand_fact.object_value,
                confidence=cand_fact.confidence,
                source_type=cand_fact.source_type,
                source_ref=source_ref,
                valid_from=cand_fact.valid_from or ev_time,
            )

            record, reinf_id, unresolved = self.conflict_resolver.resolve_and_apply_fact(
                candidate=fact_create, subject_id=subj_ent.id, event_time=ev_time, now=tx_now
            )

            if record:
                result.inserted_facts.append(record)
            if reinf_id:
                result.reinforced_facts.append(reinf_id)
            if unresolved:
                result.unresolved_conflicts.extend(unresolved)

        return result
