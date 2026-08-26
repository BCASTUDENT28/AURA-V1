"""
tests/test_ml_regime.py

Phase 7 — Regime Probability Classifier & Direction Signal Model tests.
"""

from __future__ import annotations

import math
import pytest

from backend.app.quant.features import FeatureVector
from backend.app.ml.regime_model import classify_regime_probabilities, RegimeProbabilities
from backend.app.ml.direction_model import predict_direction, DirectionSignal


def _make_feat(**overrides) -> FeatureVector:
    """Return a baseline neutral FeatureVector, with any field overridden."""
    base = dict(
        t=1_700_000_000,
        close=1000.0,
        sma9=1000.0, sma21=1000.0, sma50=1000.0, sma200=1000.0,
        ema9=1000.0, ema21=1000.0, ema50=1000.0,
        rsi14=50.0,
        macd=0.0, macdSignal=0.0, macdHist=0.0,
        atr14=10.0,
        adx14=15.0, plusDi14=18.0, minusDi14=18.0,
        bbUpper=1020.0, bbLower=980.0, bbMid=1000.0,
        bbPercentB=0.5, bbBandwidth=0.04,
        realizedVol20=0.15,
        vwap20=1000.0, vwapDevAtr=0.0, volumeZ20=0.0, relVolume20=1.0,
        return1d=0.0, return5d=0.0, return20d=0.0,
        skewness20=0.0, autocorr1=0.0,
    )
    base.update(overrides)
    return FeatureVector(**base)


# ─────────────────────────────────────────────────────────
# Regime Classifier
# ─────────────────────────────────────────────────────────

class TestRegimeClassifier:

    def test_probabilities_sum_to_one(self):
        feat = _make_feat()
        result = classify_regime_probabilities(feat)
        total = (result.BULL_TREND + result.BEAR_TREND + result.RANGE +
                 result.HIGH_VOL + result.LOW_VOL + result.BREAKOUT +
                 result.MEAN_REVERT + result.STRESS)
        assert abs(total - 1.0) < 1e-3, f"Probs sum to {total}, expected 1.0"

    def test_stress_regime_high_vol(self):
        feat = _make_feat(realizedVol20=0.38)
        result = classify_regime_probabilities(feat)
        assert result.STRESS > 0.30, f"Expected STRESS dominant, got {result.STRESS}"
        assert result.topRegime == "STRESS"

    def test_bull_trend_strong_adx_plus_di(self):
        feat = _make_feat(adx14=35.0, plusDi14=30.0, minusDi14=10.0,
                          return5d=0.06, rsi14=65.0)
        result = classify_regime_probabilities(feat)
        assert result.BULL_TREND > 0.30, f"Expected BULL_TREND dominant, got {result.BULL_TREND}"
        assert result.topRegime == "BULL_TREND"

    def test_bear_trend_strong_adx_minus_di(self):
        feat = _make_feat(adx14=35.0, plusDi14=10.0, minusDi14=30.0,
                          return5d=-0.07, rsi14=35.0)
        result = classify_regime_probabilities(feat)
        assert result.BEAR_TREND > 0.30, f"Expected BEAR_TREND dominant, got {result.BEAR_TREND}"
        assert result.topRegime == "BEAR_TREND"

    def test_range_low_adx(self):
        feat = _make_feat(adx14=12.0, bbPercentB=0.5, bbBandwidth=0.05)
        result = classify_regime_probabilities(feat)
        assert result.RANGE > 0.20, f"Expected RANGE elevated, got {result.RANGE}"

    def test_low_vol_tight_bands(self):
        feat = _make_feat(realizedVol20=0.08, bbBandwidth=0.03, adx14=10.0)
        result = classify_regime_probabilities(feat)
        assert result.LOW_VOL > 0.20, f"Expected LOW_VOL elevated, got {result.LOW_VOL}"

    def test_breakout_bb_extreme_and_volume(self):
        feat = _make_feat(bbPercentB=0.95, relVolume20=2.5, bbBandwidth=0.18)
        result = classify_regime_probabilities(feat)
        assert result.BREAKOUT > 0.25, f"Expected BREAKOUT elevated, got {result.BREAKOUT}"

    def test_all_probs_in_0_1(self):
        feat = _make_feat()
        r = classify_regime_probabilities(feat)
        for label in ["BULL_TREND", "BEAR_TREND", "RANGE", "HIGH_VOL",
                      "LOW_VOL", "BREAKOUT", "MEAN_REVERT", "STRESS"]:
            v = getattr(r, label)
            assert 0.0 <= v <= 1.0, f"{label}={v} out of [0,1]"

    def test_returns_evidence_list(self):
        feat = _make_feat(adx14=30.0, plusDi14=25.0, minusDi14=10.0)
        result = classify_regime_probabilities(feat)
        assert isinstance(result.evidence, list)
        assert len(result.evidence) >= 1

    def test_confidence_equals_top_regime_prob(self):
        feat = _make_feat(adx14=40.0, plusDi14=35.0, minusDi14=5.0, return5d=0.08)
        result = classify_regime_probabilities(feat)
        top_prob = getattr(result, result.topRegime)
        assert abs(result.confidence - top_prob) < 1e-4

    def test_calibration_temperature_present(self):
        feat = _make_feat()
        result = classify_regime_probabilities(feat)
        assert result.calibrationTemperature > 0.0


# ─────────────────────────────────────────────────────────
# Direction Signal Model
# ─────────────────────────────────────────────────────────

class TestDirectionModel:

    def test_probs_sum_to_one(self):
        feat = _make_feat()
        result = predict_direction(feat)
        total = result.probUp + result.probDown + result.probFlat
        assert abs(total - 1.0) < 1e-3, f"Probs sum to {total}"

    def test_signal_matches_dominant_prob(self):
        feat = _make_feat()
        result = predict_direction(feat)
        best = max(result.probUp, result.probDown, result.probFlat)
        if best == result.probUp:
            assert result.signal == "UP"
        elif best == result.probDown:
            assert result.signal == "DOWN"
        else:
            assert result.signal == "FLAT"

    def test_bullish_rsi_macd(self):
        feat = _make_feat(rsi14=70.0, macdHist=0.005, adx14=30.0,
                          plusDi14=28.0, minusDi14=10.0, return1d=0.012,
                          return5d=0.04, relVolume20=1.8)
        result = predict_direction(feat)
        assert result.signal == "UP", f"Expected UP, got {result.signal}"
        assert result.probUp > result.probDown

    def test_bearish_rsi_macd(self):
        feat = _make_feat(rsi14=30.0, macdHist=-0.005, adx14=30.0,
                          plusDi14=10.0, minusDi14=28.0, return1d=-0.012,
                          return5d=-0.04, relVolume20=1.8)
        result = predict_direction(feat)
        assert result.signal == "DOWN", f"Expected DOWN, got {result.signal}"
        assert result.probDown > result.probUp

    def test_confidence_in_0_1(self):
        feat = _make_feat()
        result = predict_direction(feat)
        assert 0.0 <= result.confidence <= 1.0

    def test_edge_bps_non_negative_for_directional(self):
        feat = _make_feat(rsi14=72.0, macdHist=0.006, adx14=32.0,
                          plusDi14=30.0, minusDi14=8.0)
        result = predict_direction(feat)
        if result.signal in ("UP", "DOWN"):
            assert result.edgeBps >= 0.0

    def test_flat_edge_bps_is_zero(self):
        # Near-neutral inputs should yield FLAT
        feat = _make_feat(rsi14=50.0, macdHist=0.0, adx14=10.0)
        result = predict_direction(feat)
        if result.signal == "FLAT":
            assert result.edgeBps == 0.0

    def test_all_probs_in_0_1(self):
        feat = _make_feat()
        r = predict_direction(feat)
        for p in [r.probUp, r.probDown, r.probFlat]:
            assert 0.0 <= p <= 1.0

    def test_returns_evidence_list(self):
        feat = _make_feat(rsi14=68.0, macdHist=0.003)
        result = predict_direction(feat)
        assert isinstance(result.evidence, list)
        assert len(result.evidence) >= 1
