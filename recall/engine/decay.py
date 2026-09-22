"""Decay calculator and contextual salience scoring engine for Recall."""

from datetime import datetime, timezone
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from recall.config import ensure_utc
from recall.models.fact import FactRecord
from recall.models.query import SalienceBreakdown


def calculate_retention(
    elapsed_days: float,
    reinforcements_count: int,
    base_stability_days: float = 10.0,
    alpha: float = 0.5
) -> float:
    """Calculates Ebbinghaus memory retention score R(t) = exp(-t / S).
    
    Args:
        elapsed_days: Non-negative elapsed time t in days.
        reinforcements_count: Count N of independent reinforcement events.
        base_stability_days: S_base > 0 (default: 10.0 days).
        alpha: Reinforcement stability gain factor >= 0 (default: 0.5).
        
    Returns:
        Retention score R(t) in range (0.0, 1.0].
    """
    if base_stability_days <= 0:
        raise ValueError("base_stability_days must be greater than 0.")
    if alpha < 0:
        raise ValueError("alpha must be non-negative.")

    t = max(0.0, elapsed_days)
    n = max(0, reinforcements_count)
    s = base_stability_days * (1.0 + alpha * n)

    return math.exp(-t / s)


def calculate_lexical_similarity(query_text: str, target_text: str) -> float:
    """Computes Jaccard lexical token overlap similarity in range [0.0, 1.0]."""
    q_tokens = set(re.findall(r"\w+", query_text.lower()))
    t_tokens = set(re.findall(r"\w+", target_text.lower()))
    if not q_tokens or not t_tokens:
        return 0.0
    intersection = len(q_tokens & t_tokens)
    union = len(q_tokens | t_tokens)
    return intersection / union if union > 0 else 0.0


class SalienceScorer:
    """Computes composite contextual salience scores for query results."""

    def __init__(
        self,
        weight_similarity: float = 0.4,
        weight_retention: float = 0.4,
        weight_confidence: float = 0.2,
        base_stability_days: float = 10.0,
        alpha: float = 0.5
    ):
        if weight_similarity < 0 or weight_retention < 0 or weight_confidence < 0:
            raise ValueError("All salience weights must be non-negative.")
        total_w = weight_similarity + weight_retention + weight_confidence
        if abs(total_w - 1.0) > 1e-5:
            raise ValueError(f"Salience weights must sum to 1.0 (got {total_w}).")

        self.w_sim = weight_similarity
        self.w_ret = weight_retention
        self.w_conf = weight_confidence
        self.base_stability = base_stability_days
        self.alpha = alpha

    def score_fact(
        self,
        fact: FactRecord,
        context_query: str,
        valid_at: datetime,
        reinforcements_count: int,
        latest_event_time: Optional[datetime] = None
    ) -> SalienceBreakdown:
        v_at = ensure_utc(valid_at)
        ref_time = ensure_utc(latest_event_time or fact.valid_from)

        # Elapsed days (must be non-negative)
        elapsed_sec = (v_at - ref_time).total_seconds()
        elapsed_days = max(0.0, elapsed_sec / 86400.0)

        retention = calculate_retention(
            elapsed_days=elapsed_days,
            reinforcements_count=reinforcements_count,
            base_stability_days=self.base_stability,
            alpha=self.alpha
        )

        target_str = f"{fact.predicate} {fact.object_value}"
        similarity = calculate_lexical_similarity(context_query, target_str)
        confidence = max(0.0, min(1.0, fact.confidence))

        composite = (self.w_sim * similarity) + (self.w_ret * retention) + (self.w_conf * confidence)
        composite = max(0.0, min(1.0, composite))

        return SalienceBreakdown(
            similarity=round(similarity, 4),
            retention=round(retention, 4),
            confidence=round(confidence, 4),
            composite_score=round(composite, 4)
        )
