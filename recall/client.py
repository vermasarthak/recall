"""Public client API for Recall temporal entity memory engine."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from recall.config import Clock, SystemClock, ensure_utc
from recall.db.store import StorageEngine
from recall.engine.decay import SalienceScorer
from recall.engine.extractor import BaseExtractor, FixtureExtractor
from recall.engine.ingest import EntityResolver, IngestionPipeline
from recall.engine.similarity import SimilarityProvider
from recall.models.entity import EntityCreate, EntityRecord, EntityType
from recall.models.fact import FactCreate, FactRecord, SourceType
from recall.models.query import IngestionResult, QueryResult, SalienceBreakdown


class Recall:
    """Main client interface for Recall temporal memory engine."""

    def __init__(
        self,
        db_path: str = "recall.db",
        clock: Optional[Clock] = None,
        extractor: Optional[BaseExtractor] = None,
        weight_similarity: float = 0.4,
        weight_retention: float = 0.4,
        weight_confidence: float = 0.2,
        base_stability_days: float = 10.0,
        alpha: float = 0.5,
        similarity_provider: Optional[SimilarityProvider] = None
    ):
        self.clock = clock or SystemClock()
        self.store = StorageEngine(db_path=db_path, clock=self.clock)
        self.extractor = extractor or FixtureExtractor()
        self.pipeline = IngestionPipeline(self.store, clock=self.clock)
        self.resolver = EntityResolver(self.store)
        self.salience_scorer = SalienceScorer(
            weight_similarity=weight_similarity,
            weight_retention=weight_retention,
            weight_confidence=weight_confidence,
            base_stability_days=base_stability_days,
            alpha=alpha,
            similarity_provider=similarity_provider
        )

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "Recall":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # --- ENTITY API ---

    def create_entity(
        self,
        canonical_name: str,
        type: EntityType = EntityType.PERSON,
        aliases: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> EntityRecord:
        """Creates a new entity explicitly."""
        return self.store.create_entity(
            EntityCreate(
                type=type,
                canonical_name=canonical_name,
                aliases=aliases or [],
                metadata=metadata or {}
            )
        )

    def get_entity(self, entity_id_or_name: str) -> Optional[EntityRecord]:
        """Fetches entity by ID or canonical name."""
        ent = self.store.get_entity_by_id(entity_id_or_name)
        if ent:
            return ent
        return self.store.get_entity_by_canonical_name(entity_id_or_name)

    # --- INGESTION API ---

    def ingest_turn(
        self,
        speaker: str,
        text: str,
        conversation_id: str,
        timestamp: Optional[datetime] = None,
        message_id: Optional[str] = None
    ) -> IngestionResult:
        """Ingests a conversational turn, extracts facts, resolves entities, and persists updates atomically."""
        now_time = self.clock.now()
        ev_time = ensure_utc(timestamp or now_time)
        extracted = self.extractor.extract(speaker=speaker, text=text, event_time=ev_time)
        return self.pipeline.ingest_structured_turn(
            turn=extracted,
            conv_id=conversation_id,
            message_id=message_id,
            speaker=speaker,
            event_time=ev_time,
            now=now_time
        )

    def ingest_structured(
        self,
        facts: List[FactCreate],
        conversation_id: str,
        message_id: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> IngestionResult:
        """Direct ingestion of validated structured fact assertions without LLM extraction."""
        now_time = self.clock.now()
        ev_time = ensure_utc(timestamp or now_time)

        result = IngestionResult()
        for f in facts:
            # Resolve subject
            subj_ent, _ = self.resolver.resolve(f.subject, default_type=EntityType.PERSON, now=now_time)
            f_create = FactCreate(
                subject=subj_ent.id,
                predicate=f.predicate,
                object_value=f.object_value,
                object_entity_id=f.object_entity_id,
                confidence=f.confidence,
                source_type=f.source_type,
                source_ref=f.source_ref or message_id or "structured",
                valid_from=f.valid_from or ev_time
            )
            rec, reinf, unres = self.pipeline.conflict_resolver.resolve_and_apply_fact(
                candidate=f_create,
                subject_id=subj_ent.id,
                event_time=ev_time,
                now=now_time
            )
            if rec:
                result.inserted_facts.append(rec)
            if reinf:
                result.reinforced_facts.append(reinf)
            if unres:
                result.unresolved_conflicts.extend(unres)

        return result

    # --- CORRECTION / RETRACTION API ---

    def correct_fact(
        self,
        logical_id: str,
        new_object_value: Any,
        source_ref: str,
        valid_from: Optional[datetime] = None
    ) -> FactRecord:
        """Corrects an existing logical fact by writing a revised version while preserving historical trace."""
        history = self.store.query_history(logical_id)
        if not history:
            raise ValueError(f"Logical fact ID '{logical_id}' not found.")
        target = history[-1]

        now_time = self.clock.now()
        v_from = ensure_utc(valid_from or now_time)

        f_create = FactCreate(
            subject=target.subject_id,
            predicate=target.predicate,
            object_value=new_object_value,
            confidence=1.0,
            source_type=SourceType.USER_EDIT,
            source_ref=source_ref,
            valid_from=v_from
        )
        rec, _, _ = self.pipeline.conflict_resolver.resolve_and_apply_fact(
            candidate=f_create,
            subject_id=target.subject_id,
            event_time=v_from,
            now=now_time
        )
        if not rec:
            raise RuntimeError("Failed to write correction version.")
        return rec

    def retract_fact(self, logical_id: str, source_ref: str, valid_from: Optional[datetime] = None) -> None:
        """Retracts an active logical fact without deleting historical assertion evidence."""
        history = self.store.query_history(logical_id)
        if not history:
            raise ValueError(f"Logical fact ID '{logical_id}' not found.")
        target = history[-1]

        now_time = self.clock.now()
        v_from = ensure_utc(valid_from or now_time)

        f_create = FactCreate(
            subject=target.subject_id,
            predicate=f"retract_{target.predicate}",
            object_value=target.object_value,
            confidence=1.0,
            source_type=SourceType.USER_EDIT,
            source_ref=source_ref,
            valid_from=v_from
        )
        # Apply retraction against target predicate
        f_create.predicate = target.predicate
        conn = self.store.get_connection()
        with conn:
            active_facts = self.store.query_facts(subject_id=target.subject_id, predicate=target.predicate, valid_at=v_from, known_at=now_time)
            for act in active_facts:
                if act.logical_id == logical_id:
                    self.store.close_fact_tx_to(act.version_id, tx_to=now_time, conn=conn)
                    if v_from > act.valid_from:
                        revised = FactRecord(
                            version_id=f"ver_{act.version_id[-8:]}",
                            logical_id=act.logical_id,
                            subject_id=act.subject_id,
                            predicate=act.predicate,
                            object_value=act.object_value,
                            object_entity_id=act.object_entity_id,
                            confidence=act.confidence,
                            source_type=act.source_type,
                            source_ref=source_ref,
                            valid_from=act.valid_from,
                            valid_to=v_from,
                            tx_from=now_time,
                            tx_to=None,
                            fact_hash=act.fact_hash
                        )
                        self.store.insert_fact_version(revised, conn=conn)

    def reinforce_fact(self, logical_id: str, source_ref: str, timestamp: Optional[datetime] = None) -> str:
        """Explicitly reinforces a logical fact."""
        now_time = self.clock.now()
        rf_time = ensure_utc(timestamp or now_time)
        return self.store.insert_reinforcement(logical_id, source_ref, rf_time, now_time)

    # --- QUERY API ---

    def query(
        self,
        about_entity: str,
        context: str = "",
        min_salience: float = 0.2,
        valid_at: Optional[datetime] = None,
        known_at: Optional[datetime] = None,
        as_of: Optional[datetime] = None,
        limit: int = 10
    ) -> List[QueryResult]:
        """Queries facts for an entity, computing contextual retention salience scores.
        
        Note: as_of is a backward-compatible alias for valid_at.
        """
        now_time = self.clock.now()
        v_at = ensure_utc(valid_at or as_of or now_time)
        k_at = ensure_utc(known_at or now_time)

        # Resolve entity
        ent = self.get_entity(about_entity)
        if not ent:
            return []

        active_facts = self.store.query_facts(subject_id=ent.id, valid_at=v_at, known_at=k_at)

        results: List[QueryResult] = []

        for fact in active_facts:
            # Count reinforcements visible at known_at and valid_at
            n_reinf = self.store.get_reinforcements_count(fact.logical_id, max_reinforced_at=v_at, max_tx_time=k_at)

            salience = self.salience_scorer.score_fact(
                fact=fact,
                context_query=context,
                valid_at=v_at,
                reinforcements_count=n_reinf,
                latest_event_time=fact.valid_from
            )

            if salience.composite_score >= min_salience:
                obj_ent = self.get_entity(fact.object_entity_id) if fact.object_entity_id else None
                results.append(
                    QueryResult(
                        fact=fact,
                        salience=salience,
                        subject_entity=ent,
                        object_entity=obj_ent
                    )
                )

        results.sort(key=lambda r: r.salience.composite_score, reverse=True)
        return results[:limit]

    def format_for_prompt(
        self,
        about_entity: str,
        context: str = "",
        min_salience: float = 0.2,
        valid_at: Optional[datetime] = None,
        limit: int = 10,
        max_tokens: Optional[int] = None
    ) -> str:
        """Formats the retrieved facts into a compressed XML structure optimized for LLM contexts."""
        results = self.query(about_entity, context, min_salience, valid_at, limit=limit)
        
        if not results:
            return f"<memory entity='{about_entity}'></memory>"
            
        # Heuristic: 1 token ≈ 4 characters
        max_chars = (max_tokens * 4) if max_tokens else None
        
        header = f"<memory entity='{results[0].subject_entity.canonical_name}' canonical_id='{results[0].subject_entity.id}'>"
        xml_parts = [header]
        current_chars = len(header) + len("\n</memory>")
        
        for res in results:
            v_from = res.fact.valid_from.strftime("%Y-%m-%d")
            v_to = res.fact.valid_to.strftime("%Y-%m-%d") if res.fact.valid_to else "Present"
            
            fact_str = (
                f"  <fact predicate='{res.fact.predicate}' "
                f"valid_from='{v_from}' valid_to='{v_to}' "
                f"confidence='{res.salience.confidence}' "
                f"salience='{res.salience.composite_score}'>"
                f"{res.fact.object_value}"
                f"</fact>"
            )
            
            if max_chars and (current_chars + len(fact_str) + 1) > max_chars:
                break
                
            xml_parts.append(fact_str)
            current_chars += len(fact_str) + 1
            
        xml_parts.append("</memory>")
        return "\n".join(xml_parts)

    def vacuum_history(self, retention_days: int = 30) -> int:
        """Triggers a hard delete of retracted historical facts older than the retention window."""
        return self.store.vacuum_history(retention_days)
        
    def forget(self, about_entity: str) -> int:
        """GDPR Right to be Forgotten: Permanently deletes all trace of an entity."""
        ent = self.get_entity(about_entity)
        if not ent:
            return 0
        return self.store.forget_entity(ent.id)

    def inspect_history(self, logical_id: str) -> List[FactRecord]:
        """Inspects complete version history for a logical assertion."""
        return self.store.query_history(logical_id)
