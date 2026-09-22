"""Conflict resolution, predicate cardinality policies, and versioning engine for Recall."""

from datetime import datetime
import uuid
from typing import Any, Dict, List, Optional, Tuple

from recall.config import Clock, ensure_utc
from recall.db.store import StorageEngine, calculate_fact_hash
from recall.models.fact import FactCreate, FactRecord, PredicatePolicy, SourceType


SOURCE_PRECEDENCE: Dict[SourceType, int] = {
    SourceType.USER_EDIT: 4,
    SourceType.DIRECT_STATEMENT: 3,
    SourceType.HEARSAY: 2,
    SourceType.INFERENCE: 1,
}

# Known single-valued predicates
SINGLE_VALUED_PREDICATES = {
    "primary_employer",
    "employer",
    "residence",
    "current_city",
    "marital_status",
    "relationship_status",
    "job_title",
    "favorite_color",
}


def get_predicate_policy(predicate: str) -> PredicatePolicy:
    norm = predicate.strip().lower()
    if norm.startswith("retract_") or norm == "retraction":
        return PredicatePolicy.RETRACTION
    if norm in SINGLE_VALUED_PREDICATES:
        return PredicatePolicy.SINGLE_VALUED
    return PredicatePolicy.MULTI_VALUED


class ConflictResolver:
    """Handles conflict resolution, versioning splits, and reinforcement updates atomically."""

    def __init__(self, store: StorageEngine, clock: Clock):
        self.store = store
        self.clock = clock

    def resolve_and_apply_fact(
        self,
        candidate: FactCreate,
        subject_id: str,
        object_entity_id: Optional[str] = None,
        event_time: Optional[datetime] = None,
        now: Optional[datetime] = None
    ) -> Tuple[Optional[FactRecord], Optional[str], List[Dict[str, Any]]]:
        """Resolves a candidate fact against existing versioned facts.
        
        Returns:
            (created_or_versioned_fact_record, reinforcement_logical_id, unresolved_conflicts)
        """
        conn = self.store.get_connection()
        tx_now = ensure_utc(now or self.clock.now())
        valid_start = ensure_utc(candidate.valid_from or event_time or tx_now)
        policy = get_predicate_policy(candidate.predicate)

        fact_hash = calculate_fact_hash(subject_id, candidate.predicate, candidate.object_value)

        # 1. Fetch currently active version facts (known_at=tx_now) for this subject & predicate
        active_facts = self.store.query_facts(
            subject_id=subject_id,
            predicate=candidate.predicate,
            valid_at=valid_start,
            known_at=tx_now
        )

        # Exact Duplicate Check (same fact hash)
        for active in active_facts:
            if active.fact_hash == fact_hash:
                # Add reinforcement event
                self.store.insert_reinforcement(
                    logical_fact_id=active.logical_id,
                    source_ref=candidate.source_ref,
                    reinforced_at=valid_start,
                    tx_time=tx_now
                )
                return (None, active.logical_id, [])

        if policy == PredicatePolicy.MULTI_VALUED:
            # Multi-valued: coexists cleanly
            logical_id = f"log_{uuid.uuid4().hex[:12]}"
            version_id = f"ver_{uuid.uuid4().hex[:12]}"
            new_record = FactRecord(
                version_id=version_id,
                logical_id=logical_id,
                subject_id=subject_id,
                predicate=candidate.predicate,
                object_value=candidate.object_value,
                object_entity_id=object_entity_id,
                confidence=candidate.confidence,
                source_type=candidate.source_type,
                source_ref=candidate.source_ref,
                valid_from=valid_start,
                valid_to=None,
                tx_from=tx_now,
                tx_to=None,
                fact_hash=fact_hash
            )
            self.store.insert_fact_version(new_record)
            self.store.insert_reinforcement(logical_id, candidate.source_ref, valid_start, tx_now)
            return (new_record, None, [])

        elif policy == PredicatePolicy.SINGLE_VALUED:
            # Single-valued conflict over overlapping valid intervals
            unresolved: List[Dict[str, Any]] = []
            cand_prec = SOURCE_PRECEDENCE[candidate.source_type]

            for active in active_facts:
                act_prec = SOURCE_PRECEDENCE[active.source_type]

                if cand_prec < act_prec or (cand_prec == act_prec and candidate.confidence < active.confidence):
                    # Lower precedence or lower confidence candidate cannot overwrite higher claim
                    unresolved.append({
                        "reason": "lower_precedence_or_confidence",
                        "candidate": candidate.model_dump(mode="json"),
                        "conflicting_active": active.model_dump(mode="json")
                    })
                    return (None, None, unresolved)

            # High precedence/confidence: revise existing active versions cleanly
            with conn:
                for active in active_facts:
                    # 1. Close current transaction version (tx_to = tx_now)
                    self.store.close_fact_tx_to(active.version_id, tx_to=tx_now, conn=conn)

                    # 2. Re-insert historical segment [active.valid_from, valid_start) if valid_start > active.valid_from
                    if valid_start > active.valid_from:
                        revised_old = FactRecord(
                            version_id=f"ver_{uuid.uuid4().hex[:12]}",
                            logical_id=active.logical_id,
                            subject_id=active.subject_id,
                            predicate=active.predicate,
                            object_value=active.object_value,
                            object_entity_id=active.object_entity_id,
                            confidence=active.confidence,
                            source_type=active.source_type,
                            source_ref=active.source_ref,
                            valid_from=active.valid_from,
                            valid_to=valid_start, # Closed at new fact's start time
                            tx_from=tx_now,
                            tx_to=None,
                            fact_hash=active.fact_hash
                        )
                        self.store.insert_fact_version(revised_old, conn=conn)

                # 3. Write new fact version
                logical_id = f"log_{uuid.uuid4().hex[:12]}"
                version_id = f"ver_{uuid.uuid4().hex[:12]}"
                new_record = FactRecord(
                    version_id=version_id,
                    logical_id=logical_id,
                    subject_id=subject_id,
                    predicate=candidate.predicate,
                    object_value=candidate.object_value,
                    object_entity_id=object_entity_id,
                    confidence=candidate.confidence,
                    source_type=candidate.source_type,
                    source_ref=candidate.source_ref,
                    valid_from=valid_start,
                    valid_to=None,
                    tx_from=tx_now,
                    tx_to=None,
                    fact_hash=fact_hash
                )
                self.store.insert_fact_version(new_record, conn=conn)
                self.store.insert_reinforcement(logical_id, candidate.source_ref, valid_start, tx_now, conn=conn)

            return (new_record, None, [])

        elif policy == PredicatePolicy.RETRACTION:
            # Retraction operation
            with conn:
                for active in active_facts:
                    self.store.close_fact_tx_to(active.version_id, tx_to=tx_now, conn=conn)
                    if valid_start > active.valid_from:
                        retracted = FactRecord(
                            version_id=f"ver_{uuid.uuid4().hex[:12]}",
                            logical_id=active.logical_id,
                            subject_id=active.subject_id,
                            predicate=active.predicate,
                            object_value=active.object_value,
                            object_entity_id=active.object_entity_id,
                            confidence=active.confidence,
                            source_type=active.source_type,
                            source_ref=active.source_ref,
                            valid_from=active.valid_from,
                            valid_to=valid_start,
                            tx_from=tx_now,
                            tx_to=None,
                            fact_hash=active.fact_hash
                        )
                        self.store.insert_fact_version(retracted, conn=conn)
            return (None, None, [])

        return (None, None, [])
