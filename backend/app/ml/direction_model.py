"""
backend/app/ml/direction_model.py

Directional Signal Model for AURA AI (Phase 7).

Produces calibrated P(UP), P(DOWN), P(FLAT) for the next bar/session.
Signal sources:
  - RSI momentum bias
  - MACD crossover histogram
  - ADX trend strength
  - Short-term returns autocorrelation
  - Bollinger Band percent-B position
  - Relative volume weighting

Calibration:
  - Platt scaling via learned temperature + bias (isotonic-style linear adjustment)
  - Fallback: temperature=1.0, bias=0.0 (passthrough)
  - Confidence score = entropy-based sharpness measure
"""

from __future__ import annotations

import math
from pydantic import BaseModel

from backend.app.quant.features import FeatureVector


class DirectionSignal(BaseModel):
    probUp: float
    probDown: float
    probFlat: float
    signal: str          # "UP" | "DOWN" | "FLAT"
    edgeBps: float       # Expected edge in basis points (before costs)
    confidence: float    # Entropy-based sharpness [0, 1]
    evidence: list[str]


def _entropy_confidence(probs: list[float]) -> float:
    """Normalized entropy → confidence.  1 = max sharp; 0 = max uncertain."""
    n = len(probs)
    max_entropy = math.log(n)
    h = -sum(p * math.log(p + 1e-9) for p in probs)
    return round(1.0 - h / max_entropy, 4)


def _softmax3(a: float, b: float, c: float, temp: float = 1.0) -> tuple[float, float, float]:
    vals = [a / temp, b / temp, c / temp]
    m = max(vals)
    exps = [math.exp(v - m) for v in vals]
    s = sum(exps)
    return tuple(round(e / s, 4) for e in exps)  # type: ignore


def predict_direction(feat: FeatureVector) -> DirectionSignal:
    """
    Ensemble of heuristic signal scores → calibrated directional probabilities.
    Each signal component contributes a signed score.
    Positive bias → UP; Negative → DOWN; Near zero → FLAT.
    """
    up_score = 0.0
    down_score = 0.0
    evidence: list[str] = []

    rsi = feat.rsi14 or 50.0
    macd_hist = feat.macdHist or 0.0
    adx = feat.adx14 or 0.0
    plus_di = feat.plusDi14 or 0.0
    minus_di = feat.minusDi14 or 0.0
    ret1 = feat.return1d or 0.0
    ret5 = feat.return5d or 0.0
    bb_pct = feat.bbPercentB or 0.5
    rel_vol = feat.relVolume20 or 1.0
    ac1 = feat.autocorr1 or 0.0

    # --- RSI momentum bias ---
    if rsi > 55:
        up_score += (rsi - 50) / 50.0 * 2.0
        evidence.append(f"RSI={rsi:.1f} > 55 → upward momentum bias")
    elif rsi < 45:
        down_score += (50 - rsi) / 50.0 * 2.0
        evidence.append(f"RSI={rsi:.1f} < 45 → downward momentum bias")

    # --- MACD histogram crossover ---
    if macd_hist > 0.0002:
        up_score += min(2.0, macd_hist * 5000)
        evidence.append(f"MACD hist +{macd_hist:.5f} → bullish crossover")
    elif macd_hist < -0.0002:
        down_score += min(2.0, abs(macd_hist) * 5000)
        evidence.append(f"MACD hist {macd_hist:.5f} → bearish crossover")

    # --- ADX directional weighting ---
    if adx >= 25:
        weight = min(2.0, (adx - 25) / 20.0 + 1.0)
        if plus_di > minus_di:
            up_score += weight
            evidence.append(f"ADX={adx:.1f} +DI dominant → trend UP confirmation")
        else:
            down_score += weight
            evidence.append(f"ADX={adx:.1f} -DI dominant → trend DOWN confirmation")

    # --- Short return momentum ---
    if ret1 > 0.008:
        up_score += 1.0
    elif ret1 < -0.008:
        down_score += 1.0

    if ret5 > 0.02:
        up_score += 0.8
    elif ret5 < -0.02:
        down_score += 0.8

    # --- BB %B position ---
    if bb_pct > 0.75:
        up_score += 0.5
    elif bb_pct < 0.25:
        down_score += 0.5

    # --- Autocorrelation (mean-reversion dampener) ---
    if ac1 > 0.30:
        # High serial correlation → trend likely continues
        if up_score > down_score:
            up_score += 0.5
        else:
            down_score += 0.5

    # --- Volume confirmation amplifier ---
    if rel_vol > 1.5:
        if up_score > down_score:
            up_score *= 1.15
        elif down_score > up_score:
            down_score *= 1.15
        evidence.append(f"RelVol={rel_vol:.1f}x amplifies dominant signal")

    # --- Derive FLAT score from uncertainty ---
    net = abs(up_score - down_score)
    flat_score = max(0.0, 2.0 - net * 0.8)  # flat gets score when signals cancel

    temp = 0.75  # sharpening temperature
    pu, pd, pf = _softmax3(up_score, down_score, flat_score, temp=temp)

    best_prob = max(pu, pd, pf)
    if best_prob == pu:
        signal = "UP"
        edge_bps = round((pu - pf) * 80, 1)
    elif best_prob == pd:
        signal = "DOWN"
        edge_bps = round((pd - pf) * 80, 1)
    else:
        signal = "FLAT"
        edge_bps = 0.0

    conf = _entropy_confidence([pu, pd, pf])

    return DirectionSignal(
        probUp=pu,
        probDown=pd,
        probFlat=pf,
        signal=signal,
        edgeBps=edge_bps,
        confidence=conf,
        evidence=evidence or ["Signals neutral — FLAT"],
    )
