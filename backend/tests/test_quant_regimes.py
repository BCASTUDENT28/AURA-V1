"""
backend/tests/test_quant_regimes.py

Tests for Multi-Dimensional Quant Regime Engine.
Verifies:
- Accurate classification of Bull/Bear trends, Stress, High/Low Vol, and Breakout
- Confidence scoring and trend/volatility subfactor boundedness [0.0, 1.0]
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.data.simulator import bars_of
from backend.app.quant.features import extract_features
from backend.app.quant.regime_engine import QuantRegimeEngine


def test_regime_evaluation_boundedness():
    """Regime metrics (trendStrength, volPercentile, confidence) must stay in [0.0, 1.0]."""
    for sym in ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK"]:
        bars = bars_of(sym, "1D")
        regime = QuantRegimeEngine.evaluate_bars(bars)

        assert 0.0 <= regime.trendStrength <= 1.0
        assert 0.0 <= regime.volPercentile <= 1.0
        assert 0.0 <= regime.confidence <= 1.0
        assert regime.label in [
            "BULL_TREND", "BEAR_TREND", "RANGE", "HIGH_VOL",
            "LOW_VOL", "BREAKOUT", "MEAN_REVERT", "STRESS"
        ]
        assert len(regime.notes) > 0


def test_stress_regime_trigger():
    """Realized vol > 32% must trigger STRESS regime with elevated confidence."""
    bars = bars_of("NIFTY", "1D")
    feat = extract_features(bars)
    # Force high realized volatility
    feat.realizedVol20 = 0.38

    eval_res = QuantRegimeEngine.classify(feat)
    assert eval_res.label == "STRESS"
    assert "Size down" in eval_res.notes
    assert eval_res.confidence >= 0.70


def test_bull_trend_regime_trigger():
    """High ADX (>=25) with +DI > -DI must classify as BULL_TREND."""
    bars = bars_of("RELIANCE", "1D")
    feat = extract_features(bars)
    feat.realizedVol20 = 0.16
    feat.adx14 = 32.0
    feat.plusDi14 = 28.0
    feat.minusDi14 = 14.0

    eval_res = QuantRegimeEngine.classify(feat)
    assert eval_res.label == "BULL_TREND"
    assert eval_res.trendStrength >= 0.75
