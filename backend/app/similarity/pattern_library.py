"""
backend/app/similarity/pattern_library.py

Historical Pattern Library for AURA AI (Phase 8).

Maintains a curated library of named market patterns with feature
signatures. Computes pattern match scores against live feature vectors,
producing a ranked list of activated patterns with confidence.

Pattern Library Design:
  - Each pattern is defined by a set of feature conditions (predicates)
  - Conditions are weighted; all weights in a pattern sum to 1.0
  - Match score = weighted sum of individual condition satisfaction scores
  - Score in [0, 1]; threshold > 0.70 = activated pattern

Included Patterns (NSE/F&O market relevant):
  1. MOMENTUM_SURGE          — strong ADX + volume burst + upper breakout
  2. EXHAUSTION_TOP          — overbought RSI + bearish MACD div + high vol
  3. COILING_SPRING          — low BB bandwidth + ADX flat + vol compression
  4. TREND_RESUMPTION        — pullback to EMA9/21 in uptrend after pause
  5. PANIC_CAPITULATION      — extreme negative return + vol spike + oversold
  6. VOLATILITY_CRUSH        — post-event vol collapse + BB squeeze
  7. BEAR_CONTINUATION       — retest of breakdown + ADX rising negative DI
  8. REGIME_TRANSITION       — high autocorr reversal + widening ATR
"""

from __future__ import annotations

import math
from typing import Callable, Optional

from pydantic import BaseModel

from backend.app.quant.features import FeatureVector


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

class PatternCondition(BaseModel):
    name: str
    weight: float
    score: float          # 0.0–1.0 for this condition
    satisfied: bool       # True if score > 0.5


class PatternMatch(BaseModel):
    patternId: str
    name: str
    description: str
    matchScore: float           # weighted sum, 0–1
    activated: bool             # True if matchScore > ACTIVATION_THRESHOLD
    expectedBias: str           # "BULLISH" | "BEARISH" | "NEUTRAL"
    conditions: list[PatternCondition]
    impliedAction: str


# ─────────────────────────────────────────────────────────────────────────────
# Condition helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sigmoid_score(x: float, center: float, sharpness: float = 5.0) -> float:
    """Smooth score: 1 when x >> center, 0 when x << center."""
    return round(1.0 / (1.0 + math.exp(-sharpness * (x - center))), 4)


def _threshold_score(x: float, lo: float, hi: float) -> float:
    """1.0 if lo <= x <= hi, 0 otherwise (with linear ramps at boundaries)."""
    if lo <= x <= hi:
        return 1.0
    if x < lo:
        return max(0.0, 1.0 - (lo - x) / max(lo - lo * 0.5, 1e-9))
    return max(0.0, 1.0 - (x - hi) / max(hi * 0.2, 1e-9))


# ─────────────────────────────────────────────────────────────────────────────
# Pattern Definitions
# ─────────────────────────────────────────────────────────────────────────────

ACTIVATION_THRESHOLD = 0.65


def _momentum_surge(feat: FeatureVector) -> list[tuple[str, float, float]]:
    """Strong ADX + volume surge + BB breakout — bullish continuation."""
    return [
        ("ADX > 28 (strong trend)", 0.30, _sigmoid_score(feat.adx14 or 0, 28, 0.2)),
        ("RelVol > 1.8x (volume surge)", 0.25, _sigmoid_score(feat.relVolume20 or 0, 1.8, 3.0)),
        ("BB%B > 0.80 (upper breakout)", 0.25, _sigmoid_score(feat.bbPercentB or 0, 0.80, 15.0)),
        ("+DI > -DI (bullish direction)", 0.20,
         1.0 if (feat.plusDi14 or 0) > (feat.minusDi14 or 0) else 0.0),
    ]


def _exhaustion_top(feat: FeatureVector) -> list[tuple[str, float, float]]:
    """Overbought + MACD divergence + high vol → bearish reversal risk."""
    return [
        ("RSI > 75 (overbought)", 0.30, _sigmoid_score(feat.rsi14 or 50, 75, 0.15)),
        ("MACD hist declining (negative hist)", 0.25,
         _sigmoid_score(-(feat.macdHist or 0), 0.0, 500.0)),
        ("RelVol > 1.5x (distribution)", 0.20, _sigmoid_score(feat.relVolume20 or 0, 1.5, 3.0)),
        ("Return5d > 5% (extended move)", 0.25, _sigmoid_score(feat.return5d or 0, 0.05, 30.0)),
    ]


def _coiling_spring(feat: FeatureVector) -> list[tuple[str, float, float]]:
    """Vol compression + ADX flat → impending breakout setup."""
    return [
        ("BBW < 0.06 (tight range)", 0.35, _sigmoid_score(-(feat.bbBandwidth or 0.2), -0.06, 30.0)),
        ("ADX < 18 (range)", 0.30, _sigmoid_score(-(feat.adx14 or 30), -18, 0.15)),
        ("RelVol < 0.8x (vol contraction)", 0.20,
         _sigmoid_score(-(feat.relVolume20 or 1.5), -0.8, 5.0)),
        ("RV20 < 14% (low realized vol)", 0.15,
         _sigmoid_score(-(feat.realizedVol20 or 0.3), -0.14, 20.0)),
    ]


def _trend_resumption(feat: FeatureVector) -> list[tuple[str, float, float]]:
    """Pullback to EMA9/21 in uptrend after a short pause — bullish continuation."""
    close = feat.close or 0.0
    ema9 = feat.ema9 or close
    ema21 = feat.ema21 or close
    near_ema = 1.0 - min(1.0, abs(close - ema21) / max(close * 0.01, 1.0))
    return [
        ("Price near EMA21 (pullback)", 0.30, near_ema),
        ("EMA9 > EMA21 (uptrend intact)", 0.25, 1.0 if ema9 > ema21 else 0.0),
        ("RSI 45-65 (healthy pullback)", 0.25,
         _threshold_score(feat.rsi14 or 50, 45, 65)),
        ("MACD hist > 0 (momentum positive)", 0.20,
         1.0 if (feat.macdHist or 0) > 0 else 0.0),
    ]


def _panic_capitulation(feat: FeatureVector) -> list[tuple[str, float, float]]:
    """Extreme sell-off + volume spike + oversold → mean-reversion bounce."""
    return [
        ("Return1d < -2.5% (sharp drop)", 0.30,
         _sigmoid_score(-(feat.return1d or 0), 0.025, 50.0)),
        ("RSI < 28 (deeply oversold)", 0.30,
         _sigmoid_score(-(feat.rsi14 or 50), -28, 0.15)),
        ("RelVol > 2.0x (panic selling)", 0.25,
         _sigmoid_score(feat.relVolume20 or 0, 2.0, 3.0)),
        ("BB%B < 0.10 (below lower band)", 0.15,
         _sigmoid_score(-(feat.bbPercentB or 0.5), -0.10, 20.0)),
    ]


def _volatility_crush(feat: FeatureVector) -> list[tuple[str, float, float]]:
    """Post-event vol collapse — premium sellers' opportunity."""
    return [
        ("RV20 dropping (< 13%)", 0.35,
         _sigmoid_score(-(feat.realizedVol20 or 0.3), -0.13, 20.0)),
        ("BBW contracting (< 0.07)", 0.30,
         _sigmoid_score(-(feat.bbBandwidth or 0.2), -0.07, 25.0)),
        ("RSI near 50 (balanced)", 0.20, _threshold_score(feat.rsi14 or 50, 42, 58)),
        ("RelVol < 0.7x (vol dried up)", 0.15,
         _sigmoid_score(-(feat.relVolume20 or 1.5), -0.7, 5.0)),
    ]


def _bear_continuation(feat: FeatureVector) -> list[tuple[str, float, float]]:
    """Breakdown retest + rising negative DI → bearish continuation."""
    return [
        ("-DI > +DI (bearish direction)", 0.30,
         1.0 if (feat.minusDi14 or 0) > (feat.plusDi14 or 0) else 0.0),
        ("ADX > 22 and rising (trend strength)", 0.25,
         _sigmoid_score(feat.adx14 or 0, 22, 0.15)),
        ("Return5d < -3% (sustained down)", 0.25,
         _sigmoid_score(-(feat.return5d or 0), 0.03, 30.0)),
        ("RSI < 50 (below mid)", 0.20, 1.0 if (feat.rsi14 or 50) < 50 else 0.0),
    ]


def _regime_transition(feat: FeatureVector) -> list[tuple[str, float, float]]:
    """Widening ATR + autocorr sign change → regime flip signal."""
    return [
        ("Realized vol expanding (> 22%)", 0.30,
         _sigmoid_score(feat.realizedVol20 or 0, 0.22, 20.0)),
        ("Autocorr near zero (randomness)", 0.25,
         _threshold_score(abs(feat.autocorr1 or 0), 0.0, 0.15)),
        ("ADX 15-25 (transition zone)", 0.25,
         _threshold_score(feat.adx14 or 0, 15, 25)),
        ("BBW expanding (> 0.10)", 0.20,
         _sigmoid_score(feat.bbBandwidth or 0, 0.10, 20.0)),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Pattern Registry
# ─────────────────────────────────────────────────────────────────────────────

_PATTERN_REGISTRY: list[dict] = [
    dict(id="P001", name="MOMENTUM_SURGE", bias="BULLISH",
         description="Strong ADX with volume surge and BB breakout — trend continuation",
         action="Consider momentum entry or add to existing long",
         fn=_momentum_surge),
    dict(id="P002", name="EXHAUSTION_TOP", bias="BEARISH",
         description="Overbought RSI with MACD divergence — reversal risk rising",
         action="Reduce long exposure or consider short hedge",
         fn=_exhaustion_top),
    dict(id="P003", name="COILING_SPRING", bias="NEUTRAL",
         description="Vol compression + range — breakout imminent, direction unknown",
         action="Watch for BB expansion with volume; enter on confirmed direction",
         fn=_coiling_spring),
    dict(id="P004", name="TREND_RESUMPTION", bias="BULLISH",
         description="Healthy pullback to EMA21 in uptrend — continuation setup",
         action="Higher-probability long entry on EMA21 bounce with volume",
         fn=_trend_resumption),
    dict(id="P005", name="PANIC_CAPITULATION", bias="BULLISH",
         description="Extreme oversold with volume spike — mean-reversion bounce likely",
         action="Tactical long with tight risk, watch for RSI recovery above 35",
         fn=_panic_capitulation),
    dict(id="P006", name="VOLATILITY_CRUSH", bias="NEUTRAL",
         description="Post-event vol collapse — directional edge low, premium selling window",
         action="Calendar spread or iron condor for premium capture",
         fn=_volatility_crush),
    dict(id="P007", name="BEAR_CONTINUATION", bias="BEARISH",
         description="Breakdown retest with rising -DI — bearish trend resumption",
         action="Add to short positions or exit longs on failed retest",
         fn=_bear_continuation),
    dict(id="P008", name="REGIME_TRANSITION", bias="NEUTRAL",
         description="Widening ATR + autocorr near zero — regime shift underway",
         action="Reduce size and wait for new regime to establish; avoid large positions",
         fn=_regime_transition),
]


def scan_patterns(feat: FeatureVector) -> list[PatternMatch]:
    """
    Evaluate all registered patterns against the given feature vector.
    Returns list of PatternMatch sorted by match score descending.
    """
    results: list[PatternMatch] = []

    for pattern in _PATTERN_REGISTRY:
        conditions_raw = pattern["fn"](feat)
        conditions: list[PatternCondition] = []
        weighted_sum = 0.0
        total_weight = 0.0

        for cond_name, weight, score in conditions_raw:
            conditions.append(PatternCondition(
                name=cond_name,
                weight=round(weight, 3),
                score=round(score, 4),
                satisfied=score > 0.5,
            ))
            weighted_sum += weight * score
            total_weight += weight

        match_score = round(weighted_sum / max(total_weight, 1e-9), 4)

        results.append(PatternMatch(
            patternId=pattern["id"],
            name=pattern["name"],
            description=pattern["description"],
            matchScore=match_score,
            activated=match_score >= ACTIVATION_THRESHOLD,
            expectedBias=pattern["bias"],
            conditions=conditions,
            impliedAction=pattern["action"],
        ))

    results.sort(key=lambda x: x.matchScore, reverse=True)
    return results
