"""
backend/app/quant/regime_engine.py

Multi-Dimensional Quant Regime Engine for AURA AI.
Evaluates market state across Volatility, Trend, Volume, and Return Distribution.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel

from backend.app.quant.features import FeatureVector, extract_features
from backend.app.schemas.types import Bar, Regime, RegimeLabel


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
    """Multi-factor regime classification engine."""

    @staticmethod
    def classify(features: FeatureVector) -> RegimeEvaluation:
        vol = features.realizedVol20
        adx = features.adx14
        rsi = features.rsi14
        rv = features.relVolume20
        px = features.close
        sma50 = features.sma50
        sma200 = features.sma200

        # Sub-factors
        trend_score = min(1.0, adx / 40.0)
        vol_score = max(0.0, min(1.0, (vol - 0.08) / 0.28))
        vol_expansion = 1.0 if rv > 1.3 else 0.5
        ma_alignment = 1.0 if (features.sma9 > features.sma21 > features.sma50) else (-1.0 if (features.sma9 < features.sma21 < features.sma50) else 0.0)

        label: RegimeLabel = "RANGE"
        notes = "ADX below trend threshold; price in consolidation range."
        confidence = 0.60

        if vol > 0.32:
            label = "STRESS"
            notes = f"Realized vol {vol * 100:.1f}% in tail (>32%). Size down; protect open capital."
            confidence = min(0.95, 0.70 + (vol - 0.32) * 2)
        elif vol > 0.24:
            label = "HIGH_VOL"
            notes = f"Elevated realized volatility ({vol * 100:.1f}%). Widen stops; fade false breakouts."
            confidence = 0.80
        elif vol < 0.10 and adx < 18:
            label = "LOW_VOL"
            notes = f"Compressed volatility ({vol * 100:.1f}%). Coiling market; breakout watch."
            confidence = 0.75
        elif adx >= 25 and features.plusDi14 > features.minusDi14:
            label = "BULL_TREND"
            notes = f"ADX {adx:.1f} confirms bull trend with +DI lead ({features.plusDi14:.1f} vs {features.minusDi14:.1f})."
            confidence = min(0.90, 0.55 + adx / 80)
        elif adx >= 25 and features.minusDi14 > features.plusDi14:
            label = "BEAR_TREND"
            notes = f"ADX {adx:.1f} confirms bear trend with -DI lead ({features.minusDi14:.1f} vs {features.plusDi14:.1f})."
            confidence = min(0.90, 0.55 + adx / 80)
        elif adx >= 20 and rv > 1.4 and abs(rsi - 50) > 12:
            label = "BREAKOUT"
            notes = f"Volume expansion (RV {rv:.2f}x) with directional momentum (RSI {rsi:.0f})."
            confidence = 0.78
        elif adx < 20 and 30 < rsi < 70:
            label = "MEAN_REVERT"
            notes = f"Range-bound regime with neutral oscillator (RSI {rsi:.0f}). Mean-reversion favored."
            confidence = 0.70
        else:
            label = "RANGE"
            confidence = 0.65

        return RegimeEvaluation(
            label=label,
            adx=adx,
            realizedVol=vol,
            volPercentile=round(vol_score, 4),
            trendStrength=round(trend_score, 4),
            notes=notes,
            confidence=round(confidence, 4),
            subFactors={
                "trendScore": round(trend_score, 4),
                "volScore": round(vol_score, 4),
                "volumeExpansion": round(vol_expansion, 4),
                "maAlignment": round(ma_alignment, 4),
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
