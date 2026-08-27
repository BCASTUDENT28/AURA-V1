"""
backend/app/quant/regime_engine.py

Multi-Dimensional Quant Regime Engine for AURA AI.
Evaluates market state across Volatility, Trend, Volume, and Return Distribution.

Delegation contract
-------------------
Core regime label + notes logic lives in a SINGLE place:
  engines/decision/regime._classify_from_scalars()

This class accepts a FeatureVector (already-computed scalars), delegates the
classification chain to _classify_from_scalars(), then adds the extra fields
(confidence, subFactors) that the quant API layer needs.  No classification
thresholds are duplicated here.
"""

from __future__ import annotations

from pydantic import BaseModel

from backend.app.quant.features import FeatureVector, extract_features
from backend.app.schemas.types import Bar, Regime, RegimeLabel
from backend.app.engines.decision.regime import _classify_from_scalars


class RegimeEvaluation(BaseModel):
    label: RegimeLabel
    adx: float
    realizedVol: float
    volPercentile: float
    trendStrength: float
    notes: str
    confidence: float
    subFactors: dict[str, float]


class QuantRegimeEngine:
    """Multi-factor regime classification engine.

    Uses _classify_from_scalars() from engines/decision/regime as the
    canonical if-elif chain. Adds confidence and subFactors on top.
    """

    @staticmethod
    def classify(features: FeatureVector) -> RegimeEvaluation:
        vol = features.realizedVol20
        adx = features.adx14
        rv = features.relVolume20

        # ── Single source of truth for label + notes ──────────────────────────
        regime: Regime = _classify_from_scalars(
            vol=vol,
            adx=adx,
            plus_di=features.plusDi14,
            minus_di=features.minusDi14,
            rel_vol=features.relVolume20,
            rsi=features.rsi14,
        )
        label: RegimeLabel = regime.label
        notes: str = regime.notes

        # ── Extra fields computed by this layer ───────────────────────────────
        trend_score = min(1.0, adx / 40.0)
        vol_score = max(0.0, min(1.0, (vol - 0.08) / 0.28))
        vol_expansion = 1.0 if rv > 1.3 else 0.5
        ma_alignment = (
            1.0
            if (features.sma9 > features.sma21 > features.sma50)
            else (-1.0 if (features.sma9 < features.sma21 < features.sma50) else 0.0)
        )

        _confidence_map: dict[str, float] = {
            "STRESS":      min(0.95, 0.70 + max(0.0, vol - 0.32) * 2),
            "HIGH_VOL":    0.80,
            "LOW_VOL":     0.75,
            "BULL_TREND":  min(0.90, 0.55 + adx / 80),
            "BEAR_TREND":  min(0.90, 0.55 + adx / 80),
            "BREAKOUT":    0.78,
            "MEAN_REVERT": 0.70,
            "RANGE":       0.65,
        }
        confidence = _confidence_map.get(label, 0.65)

        return RegimeEvaluation(
            label=label,
            adx=adx,
            realizedVol=vol,
            volPercentile=round(vol_score, 4),
            trendStrength=round(trend_score, 4),
            notes=notes,
            confidence=round(confidence, 4),
            subFactors={
                "trendScore":      round(trend_score, 4),
                "volScore":        round(vol_score, 4),
                "volumeExpansion": round(vol_expansion, 4),
                "maAlignment":     round(ma_alignment, 4),
            },
        )

    @classmethod
    def evaluate_bars(cls, bars: list[Bar]) -> RegimeEvaluation:
        features = extract_features(bars)
        return cls.classify(features)

    @classmethod
    def to_schema_regime(cls, eval_res: RegimeEvaluation) -> Regime:
        return Regime(
            label=eval_res.label,
            adx=eval_res.adx,
            realizedVol=eval_res.realizedVol,
            volPercentile=eval_res.volPercentile,
            trendStrength=eval_res.trendStrength,
            notes=eval_res.notes,
        )
