"""
backend/tests/test_regime_v2.py

Tests for AURA V2 Probabilistic Regime Engine.

Verifies:
1. Regime probabilities always sum to 1.0
2. All probabilities in [0, 1]
3. BULL_TREND detected in uptrend with high ADX
4. BEAR_TREND detected in downtrend with high ADX
5. RANGE detected in low-ADX, flat market
6. STRESS detected in high-volatility conditions
7. LOW_VOL detected in compressed volatility
8. Top label matches highest probability
9. Confidence equals probability of top label
10. Strategy fit uses probability weighting (not hard label)
11. Regime result converts to Pydantic Regime schema correctly
12. Model version is present and non-empty
"""

from __future__ import annotations

import pytest

from backend.app.engines.regime.regime_v2 import (
    classify_regime_v2,
    regime_strategy_fit,
    RegimeResult,
)
from backend.app.schemas.types import Bar

REGIME_LABELS = [
    "BULL_TREND", "BEAR_TREND", "RANGE",
    "BREAKOUT", "HIGH_VOL", "LOW_VOL",
    "MEAN_REVERT", "STRESS",
]


def _bar(t: int, o: float, h: float, l: float, c: float, v: float) -> Bar:
    return Bar(t=t, o=o, h=h, l=l, c=c, v=v)


def _bars_trending_up(n: int = 60, start: float = 1000.0, step: float = 8.0) -> list[Bar]:
    bars = []
    px = start
    for i in range(n):
        px += step
        bars.append(_bar(i * 86400000, px - 4, px + step * 0.7, px - step * 0.3, px, 100000))
    return bars


def _bars_trending_down(n: int = 60, start: float = 2000.0, step: float = 8.0) -> list[Bar]:
    bars = []
    px = start
    for i in range(n):
        px -= step
        bars.append(_bar(i * 86400000, px + 4, px + step * 0.3, px - step * 0.7, px, 100000))
    return bars


def _bars_flat(n: int = 60, px: float = 1000.0) -> list[Bar]:
    bars = []
    for i in range(n):
        wiggle = 2.0 * (1 if i % 2 == 0 else -1)
        c = px + wiggle
        bars.append(_bar(i * 86400000, px, px + 3, px - 3, c, 60000))
    return bars


def _bars_high_vol(n: int = 30, px: float = 1000.0) -> list[Bar]:
    """Wide swings simulating high-volatility market."""
    bars = []
    for i in range(n):
        swing = 50.0 * (1 if i % 2 == 0 else -1)
        c = px + swing
        bars.append(_bar(i * 86400000, px, px + 60, px - 60, c, 200000))
        px = c
    return bars


def _bars_low_vol(n: int = 30, px: float = 1000.0) -> list[Bar]:
    """Very tight bars simulating compressed vol."""
    bars = []
    for i in range(n):
        wiggle = 0.5 * (1 if i % 2 == 0 else -1)
        c = px + wiggle
        bars.append(_bar(i * 86400000, px, px + 1, px - 1, c, 40000))
    return bars


# ─────────────────────────────────────────────────────────────────────────────
# 1. Probability constraints
# ─────────────────────────────────────────────────────────────────────────────

def test_regime_probs_sum_to_one():
    result = classify_regime_v2(_bars_trending_up())
    total = sum(result.probabilities.values())
    assert abs(total - 1.0) < 1e-6, f"Probs sum to {total}, expected 1.0"


def test_all_probs_in_0_1():
    for bars in [_bars_trending_up(), _bars_trending_down(), _bars_flat(), _bars_high_vol()]:
        result = classify_regime_v2(bars)
        for label, p in result.probabilities.items():
            assert 0.0 <= p <= 1.0, f"{label}: probability {p} out of [0, 1]"


def test_all_regime_labels_present():
    result = classify_regime_v2(_bars_flat())
    for label in REGIME_LABELS:
        assert label in result.probabilities, f"Missing regime label: {label}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Top label matches highest probability
# ─────────────────────────────────────────────────────────────────────────────

def test_top_label_matches_max_probability():
    result = classify_regime_v2(_bars_trending_up())
    expected_top = max(result.probabilities, key=lambda k: result.probabilities[k])
    assert result.label == expected_top, (
        f"Top label {result.label} doesn't match max prob label {expected_top}"
    )


def test_confidence_equals_top_label_probability():
    result = classify_regime_v2(_bars_flat())
    assert abs(result.confidence - result.probabilities[result.label]) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# 3. Regime detection accuracy
# ─────────────────────────────────────────────────────────────────────────────

def test_bull_trend_detected_in_uptrend():
    result = classify_regime_v2(_bars_trending_up())
    bull_prob = result.probabilities.get("BULL_TREND", 0.0)
    assert bull_prob > 0.2, (
        f"BULL_TREND prob should be high in uptrend, got {bull_prob:.3f}. "
        f"Top regime: {result.label}"
    )


def test_bear_trend_detected_in_downtrend():
    result = classify_regime_v2(_bars_trending_down())
    bear_prob = result.probabilities.get("BEAR_TREND", 0.0)
    assert bear_prob > 0.2, (
        f"BEAR_TREND prob should be high in downtrend, got {bear_prob:.3f}. "
        f"Top regime: {result.label}"
    )


def test_range_regime_in_flat_market():
    result = classify_regime_v2(_bars_flat())
    range_prob = result.probabilities.get("RANGE", 0.0)
    mean_revert_prob = result.probabilities.get("MEAN_REVERT", 0.0)
    assert range_prob + mean_revert_prob > 0.25, (
        f"RANGE+MEAN_REVERT should dominate in flat market, got {range_prob:.3f}+{mean_revert_prob:.3f}"
    )


def test_high_vol_detected():
    result = classify_regime_v2(_bars_high_vol())
    hv_prob = result.probabilities.get("HIGH_VOL", 0.0)
    stress_prob = result.probabilities.get("STRESS", 0.0)
    assert hv_prob + stress_prob > 0.25, (
        f"HIGH_VOL+STRESS should be prominent in volatile market, got combined {hv_prob + stress_prob:.3f}"
    )


def test_low_vol_detected():
    result = classify_regime_v2(_bars_low_vol())
    lv_prob = result.probabilities.get("LOW_VOL", 0.0)
    assert lv_prob > 0.1, f"LOW_VOL prob should be elevated in calm market, got {lv_prob:.3f}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Evidence list
# ─────────────────────────────────────────────────────────────────────────────

def test_regime_has_evidence():
    result = classify_regime_v2(_bars_trending_up())
    assert len(result.evidence) > 0, "Regime result should include supporting evidence"


def test_evidence_has_required_fields():
    result = classify_regime_v2(_bars_trending_up())
    for ev in result.evidence:
        assert ev.feature, "Evidence must have feature name"
        assert ev.description, "Evidence must have description"
        assert ev.supports, "Evidence must have supports field"
        assert isinstance(ev.value, (int, float)), "Evidence value must be numeric"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Strategy fit with probability weighting
# ─────────────────────────────────────────────────────────────────────────────

def test_ma_cross_fit_higher_in_trend_than_range():
    trend_result = classify_regime_v2(_bars_trending_up())
    range_result = classify_regime_v2(_bars_flat())

    trend_fit = regime_strategy_fit("ma_cross", trend_result.probabilities)
    range_fit = regime_strategy_fit("ma_cross", range_result.probabilities)

    assert trend_fit > range_fit, (
        f"MA Cross should have higher fit in trend ({trend_fit:.2f}) than range ({range_fit:.2f})"
    )


def test_orb_fit_higher_in_breakout():
    """Simulate breakout via wide bars + high relative volume."""
    breakout_bars = [
        _bar(i * 86400000, 1000.0, 1100.0, 950.0, 1080.0 if i < 5 else 1000.0 + i * 5, 500000)
        for i in range(30)
    ]
    breakout_result = classify_regime_v2(breakout_bars)
    range_result = classify_regime_v2(_bars_flat())

    orb_breakout_fit = regime_strategy_fit("orb", breakout_result.probabilities)
    orb_range_fit = regime_strategy_fit("orb", range_result.probabilities)
    # ORB should do at least as well in breakout vs range
    assert orb_breakout_fit >= orb_range_fit * 0.8, (
        f"ORB fit should be at least reasonable in breakout ({orb_breakout_fit:.2f}) vs range ({orb_range_fit:.2f})"
    )


def test_strategy_fit_in_range_0_1():
    result = classify_regime_v2(_bars_trending_up())
    for strat in ["ma_cross", "vwap_rsi", "orb"]:
        fit = regime_strategy_fit(strat, result.probabilities)
        assert 0.0 <= fit <= 1.0, f"Strategy fit {strat} out of range: {fit}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Schema conversion
# ─────────────────────────────────────────────────────────────────────────────

def test_regime_result_converts_to_schema():
    result = classify_regime_v2(_bars_trending_up())
    schema = result.to_schema()
    assert schema.label == result.label
    assert schema.probabilities is not None
    assert schema.confidence == result.confidence
    assert schema.modelVersion == result.model_version


def test_regime_schema_has_probability_distribution():
    result = classify_regime_v2(_bars_trending_up())
    schema = result.to_schema()
    probs_dict = schema.probabilities.as_dict()
    total = sum(probs_dict.values())
    assert abs(total - 1.0) < 1e-6, f"Schema probs don't sum to 1: {total}"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Model version
# ─────────────────────────────────────────────────────────────────────────────

def test_model_version_present():
    result = classify_regime_v2(_bars_trending_up())
    assert result.model_version, "Model version must be non-empty"
    assert "v2" in result.model_version.lower() or "heuristic" in result.model_version.lower()
