"""Tests for Ebbinghaus retention decay, reinforcement calculation, and contextual salience scoring."""

import math

import pytest

from recall.engine.decay import SalienceScorer, calculate_lexical_similarity, calculate_retention


def test_decay_math_exact_spec_values():
    # 1. S_base = 1.0, alpha = 0, N = 0 -> S = 1.0
    # t = 60 days -> R(60) = exp(-60) < 0.1
    r_60 = calculate_retention(elapsed_days=60.0, reinforcements_count=0, base_stability_days=1.0, alpha=0.0)
    assert r_60 < 0.1
    assert math.isclose(r_60, math.exp(-60.0))

    # t = 1 day -> R(1) = exp(-1) ≈ 0.367879...
    r_1_s1 = calculate_retention(elapsed_days=1.0, reinforcements_count=0, base_stability_days=1.0, alpha=0.0)
    assert math.isclose(r_1_s1, math.exp(-1.0), abs_tol=1e-4)
    assert abs(r_1_s1 - 0.3679) < 0.001

    # 2. S_base = 10.0, alpha = 0, N = 0 -> S = 10.0
    # t = 1 day -> R(1) = exp(-0.1) ≈ 0.904837...
    r_1_s10 = calculate_retention(elapsed_days=1.0, reinforcements_count=0, base_stability_days=10.0, alpha=0.0)
    assert math.isclose(r_1_s10, math.exp(-0.1), abs_tol=1e-4)
    assert abs(r_1_s10 - 0.9048) < 0.001


def test_reinforcement_monotonicity():
    # Higher reinforcement N yields higher retention R(t)
    r_n0 = calculate_retention(elapsed_days=30.0, reinforcements_count=0, base_stability_days=10.0, alpha=0.5)
    r_n2 = calculate_retention(elapsed_days=30.0, reinforcements_count=2, base_stability_days=10.0, alpha=0.5)
    r_n5 = calculate_retention(elapsed_days=30.0, reinforcements_count=5, base_stability_days=10.0, alpha=0.5)

    assert r_n0 < r_n2 < r_n5


def test_salience_weights_validation():
    # Sum must equal 1.0
    with pytest.raises(ValueError, match="must sum to 1.0"):
        SalienceScorer(weight_similarity=0.5, weight_retention=0.5, weight_confidence=0.5)

    # Weights must be non-negative
    with pytest.raises(ValueError, match="must be non-negative"):
        SalienceScorer(weight_similarity=-0.1, weight_retention=0.6, weight_confidence=0.5)


def test_lexical_similarity():
    sim1 = calculate_lexical_similarity("working at Google", "primary_employer Google")
    assert sim1 > 0.0

    sim_zero = calculate_lexical_similarity("apples and oranges", "primary_employer Google")
    assert sim_zero == 0.0
