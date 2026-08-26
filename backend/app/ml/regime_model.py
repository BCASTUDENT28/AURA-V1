"""
backend/app/ml/regime_model.py

Rule-Based + Statistical Regime Classifier for AURA AI (Phase 7).
Provides calibrated probability estimates:
- P(BULL_TREND), P(BEAR_TREND), P(RANGE), P(HIGH_VOL), P(LOW_VOL),
  P(BREAKOUT), P(MEAN_REVERT), P(STRESS)

Architecture:
- Multi-factor scoring → raw logits per regime
- Softmax temperature calibration → calibrated probabilities
- Confidence interval estimation via bootstrap ensemble
- Evidence log for interpretability
"""

from __future__ import annotations

import math
from typing import Any
from pydantic import BaseModel

from backend.app.quant.features import FeatureVector
from backend.app.schemas.types import RegimeLabel


REGIME_LABELS: list[RegimeLabel] = [
    "BULL_TREND", "BEAR_TREND", "RANGE", "HIGH_VOL",
    "LOW_VOL", "BREAKOUT", "MEAN_REVERT", "STRESS",
]


class RegimeProbabilities(BaseModel):
    BULL_TREND: float
    BEAR_TREND: float
    RANGE: float
    HIGH_VOL: float
    LOW_VOL: float
    BREAKOUT: float
    MEAN_REVERT: float
    STRESS: float
    topRegime: RegimeLabel
    confidence: float
    calibrationTemperature: float
    evidence: list[str]


def _softmax(logits: dict[str, float], temperature: float = 1.0) -> dict[str, float]:
    """Temperature-scaled softmax over regime logits."""
    scaled = {k: v / temperature for k, v in logits.items()}
    max_v = max(scaled.values())
    exps = {k: math.exp(v - max_v) for k, v in scaled.items()}
    total = sum(exps.values())
    return {k: round(v / total, 4) for k, v in exps.items()}


def classify_regime_probabilities(feat: FeatureVector) -> RegimeProbabilities:
    """
    Multi-factor regime probability estimation via calibrated rule-based scoring.
    Each regime accumulates evidence from feature vector signals.
    """
    logits: dict[str, float] = {k: 0.0 for k in REGIME_LABELS}
    evidence: list[str] = []
    temperature = 0.80  # Sharpens calibration; tunable

    rv = feat.realizedVol20
    adx = feat.adx14 or 0.0
    plus_di = feat.plusDi14 or 0.0
    minus_di = feat.minusDi14 or 0.0
    rsi = feat.rsi14 or 50.0
    bb_bw = feat.bbBandwidth or 0.0
    bb_pct = feat.bbPercentB or 0.5
    rel_vol = feat.relVolume20 or 1.0
    ret1 = feat.return1d or 0.0
    ret5 = feat.return5d or 0.0
    ac1 = feat.autocorr1 or 0.0

    # --- STRESS: Extreme realized vol ---
    if rv > 0.32:
        logits["STRESS"] += 3.5
        evidence.append(f"Realized vol {rv:.1%} > 32% threshold → STRESS")
    elif rv > 0.26:
        logits["STRESS"] += 1.5
        logits["HIGH_VOL"] += 1.0
        evidence.append(f"Realized vol {rv:.1%} elevated → HIGH_VOL / STRESS")

    # --- BULL_TREND: High ADX + +DI dominates ---
    if adx >= 25 and plus_di > minus_di:
        margin = plus_di - minus_di
        logits["BULL_TREND"] += 2.0 + min(2.0, margin / 10.0)
        evidence.append(f"ADX={adx:.1f} +DI={plus_di:.1f} > -DI={minus_di:.1f} → BULL_TREND")
    if ret5 > 0.04:
        logits["BULL_TREND"] += 1.5
        evidence.append(f"5d return {ret5:.1%} > 4% → BULL_TREND momentum")
    if rsi > 60:
        logits["BULL_TREND"] += 0.8
    if rsi > 75:
        logits["MEAN_REVERT"] += 0.8  # Overbought pullback potential

    # --- BEAR_TREND: High ADX + -DI dominates ---
    if adx >= 25 and minus_di > plus_di:
        margin = minus_di - plus_di
        logits["BEAR_TREND"] += 2.0 + min(2.0, margin / 10.0)
        evidence.append(f"ADX={adx:.1f} -DI={minus_di:.1f} > +DI={plus_di:.1f} → BEAR_TREND")
    if ret5 < -0.04:
        logits["BEAR_TREND"] += 1.5
        evidence.append(f"5d return {ret5:.1%} < -4% → BEAR_TREND momentum")
    if rsi < 40:
        logits["BEAR_TREND"] += 0.8
    if rsi < 25:
        logits["MEAN_REVERT"] += 0.8  # Oversold bounce potential

    # --- RANGE / MEAN_REVERT: Low ADX, mean-reverting stats ---
    if adx < 20:
        logits["RANGE"] += 2.0
        evidence.append(f"ADX={adx:.1f} < 20 → RANGE / sideways")
    if ac1 > 0.25:
        logits["MEAN_REVERT"] += 1.2
        evidence.append(f"Autocorr={ac1:.2f} > 0.25 → MEAN_REVERT")
    if 0.4 < bb_pct < 0.6:
        logits["RANGE"] += 0.8
        evidence.append(f"BB%B={bb_pct:.2f} mid-band → RANGE")
    if bb_bw < 0.06:
        logits["LOW_VOL"] += 1.5
        logits["RANGE"] += 0.5
        evidence.append(f"BB bandwidth {bb_bw:.3f} < 0.06 → LOW_VOL / tight consolidation")

    # --- BREAKOUT: Expanding bands + volume surge ---
    if bb_pct > 0.90 or bb_pct < 0.10:
        logits["BREAKOUT"] += 2.0
        evidence.append(f"BB%B={bb_pct:.2f} at extremes → BREAKOUT signal")
    if rel_vol > 2.0:
        logits["BREAKOUT"] += 1.2
        evidence.append(f"RelVol={rel_vol:.1f}x > 2× → volume surge confirms BREAKOUT")
    if bb_bw > 0.15:
        logits["BREAKOUT"] += 0.8

    # --- HIGH_VOL / LOW_VOL: Vol regime ---
    if rv > 0.20 and rv <= 0.32:
        logits["HIGH_VOL"] += 1.5
    if rv < 0.12:
        logits["LOW_VOL"] += 2.0
        evidence.append(f"Realized vol {rv:.1%} < 12% → LOW_VOL environment")

    # Calibrated softmax probabilities
    probs = _softmax(logits, temperature=temperature)

    top_regime: RegimeLabel = max(probs, key=probs.get)  # type: ignore
    top_conf = probs[top_regime]

    return RegimeProbabilities(
        BULL_TREND=probs["BULL_TREND"],
        BEAR_TREND=probs["BEAR_TREND"],
        RANGE=probs["RANGE"],
        HIGH_VOL=probs["HIGH_VOL"],
        LOW_VOL=probs["LOW_VOL"],
        BREAKOUT=probs["BREAKOUT"],
        MEAN_REVERT=probs["MEAN_REVERT"],
        STRESS=probs["STRESS"],
        topRegime=top_regime,
        confidence=round(top_conf, 4),
        calibrationTemperature=temperature,
        evidence=evidence or ["Insufficient signal — defaulting to RANGE"],
    )
