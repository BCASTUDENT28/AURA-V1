"""
backend/app/engines/regime/regime_v2.py

AURA V2 Regime Engine — Probabilistic Multi-Regime Classifier
=============================================================

V1 regime engine returned a single hard label.
V2 returns a full probability distribution across all 8 regime labels.

Design:
  - Uses a scoring function per regime based on feature evidence
  - Applies softmax over scores → probabilities summing to 1.0
  - Returns RegimeResult with label, probabilities, confidence, supporting evidence
  - Pluggable: future trained models can implement the same interface

Regimes:
  BULL_TREND   — strong upward directional trend (high ADX, +DI > -DI)
  BEAR_TREND   — strong downward directional trend (high ADX, -DI > +DI)
  RANGE        — low trend, oscillating price (low ADX, mid RSI)
  BREAKOUT     — range expansion with volume (BB width widening, vol expansion)
  HIGH_VOL     — elevated realized volatility without clear direction
  LOW_VOL      — compressed volatility (coiling, potential energy)
  MEAN_REVERT  — oversold/overbought extremes with mean-reversion setup
  STRESS       — tail volatility, extreme conditions (possible crisis/news)

Model version: regime-v2-heuristic
Next version: regime-v3-trained (ML trained model replacing this)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from backend.app.features.engine import FeatureVector, extract_features
from backend.app.schemas.types import Bar, Regime, RegimeLabel, RegimeProbabilities

MODEL_VERSION = "regime-v2-heuristic"
REGIME_LABELS: list[RegimeLabel] = [
    "BULL_TREND", "BEAR_TREND", "RANGE",
    "BREAKOUT", "HIGH_VOL", "LOW_VOL",
    "MEAN_REVERT", "STRESS",
]


@dataclass
class RegimeEvidence:
    """Supporting evidence for a regime classification."""
    feature: str
    value: float
    supports: str          # which regime(s) this supports
    description: str


@dataclass
class RegimeResult:
    """
    Full probabilistic regime output.
    Replaces single-label Regime with uncertainty-aware distribution.
    """
    label: RegimeLabel                        # top regime
    probabilities: dict[str, float]           # all 8 regime probs (sum to 1.0)
    confidence: float                         # probability of top label [0, 1]
    adx: float
    realized_vol: float
    vol_percentile: float
    trend_strength: float
    notes: str
    evidence: list[RegimeEvidence] = field(default_factory=list)
    model_version: str = MODEL_VERSION

    def to_schema(self) -> Regime:
        """Convert to Pydantic Regime schema (backward compatible)."""
        probs = RegimeProbabilities(**{k: v for k, v in self.probabilities.items()})
        return Regime(
            label=self.label,
            probabilities=probs,
            confidence=self.confidence,
            adx=self.adx,
            realizedVol=self.realized_vol,
            volPercentile=self.vol_percentile,
            trendStrength=self.trend_strength,
            notes=self.notes,
            modelVersion=self.model_version,
        )


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    """Convert raw scores to probabilities via softmax."""
    max_s = max(scores.values()) if scores else 0.0
    exps = {k: math.exp(v - max_s) for k, v in scores.items()}
    total = sum(exps.values())
    return {k: v / total for k, v in exps.items()} if total else {k: 1.0 / len(scores) for k in scores}


def _score_regimes(fv: FeatureVector) -> tuple[dict[str, float], list[RegimeEvidence]]:
    """
    Score each regime using feature evidence.
    Returns (scores_dict, evidence_list).
    Scores are unnormalized — softmax converts to probabilities.
    """
    scores: dict[str, float] = {label: 0.0 for label in REGIME_LABELS}
    evidence: list[RegimeEvidence] = []

    adx = fv.adx
    vol = fv.realized_vol
    rsi = fv.rsi
    rel_vol = fv.rel_volume
    bb_width = fv.bb_width
    vol_exp = fv.vol_expansion
    plus_di = fv.plus_di
    minus_di = fv.minus_di
    roc = fv.roc_10
    persistence = fv.momentum_persistence
    slope = fv.trend_slope
    hh = fv.higher_highs
    range_comp = fv.range_compression
    vwap_dist = fv.vwap_distance

    # ── STRESS: extreme volatility tail ─────────────────────────────────────
    if vol > 0.30:
        s = (vol - 0.30) / 0.10 * 3.0  # 0→3 over range 0.30→0.40
        scores["STRESS"] += s
        evidence.append(RegimeEvidence(
            feature="realized_vol", value=vol,
            supports="STRESS",
            description=f"Realized vol {vol:.1%} > 30% — tail volatility condition"
        ))

    if vol > 0.20:
        scores["STRESS"] += 0.5
        scores["HIGH_VOL"] += 1.0

    # ── HIGH_VOL: elevated but sub-stress volatility ─────────────────────────
    if 0.18 < vol <= 0.30:
        s = (vol - 0.18) / 0.12 * 2.0
        scores["HIGH_VOL"] += s
        evidence.append(RegimeEvidence(
            feature="realized_vol", value=vol,
            supports="HIGH_VOL",
            description=f"Realized vol {vol:.1%} — elevated volatility"
        ))

    # ── LOW_VOL: compressed volatility ───────────────────────────────────────
    if vol < 0.10:
        s = (0.10 - vol) / 0.10 * 2.0
        scores["LOW_VOL"] += s
        evidence.append(RegimeEvidence(
            feature="realized_vol", value=vol,
            supports="LOW_VOL",
            description=f"Realized vol {vol:.1%} — compressed, potential energy building"
        ))

    if adx < 15 and vol < 0.12:
        scores["LOW_VOL"] += 1.0
        evidence.append(RegimeEvidence(
            feature="adx", value=adx,
            supports="LOW_VOL",
            description=f"ADX {adx:.1f} + low vol → coiling pattern"
        ))

    # ── BULL_TREND ────────────────────────────────────────────────────────────
    if adx >= 20:
        di_bias = plus_di - minus_di
        if di_bias > 0:
            s = min(adx / 40, 1.0) * (di_bias / 30) * 3.0
            scores["BULL_TREND"] += s
            evidence.append(RegimeEvidence(
                feature="adx+plus_di", value=di_bias,
                supports="BULL_TREND",
                description=f"ADX {adx:.1f}, +DI leads by {di_bias:.1f}"
            ))

    if slope > 0.002:
        scores["BULL_TREND"] += min(slope / 0.01, 1.0) * 1.5
        evidence.append(RegimeEvidence(
            feature="trend_slope", value=slope,
            supports="BULL_TREND",
            description=f"Positive trend slope {slope:.4f}"
        ))

    if hh > 0.5:
        scores["BULL_TREND"] += hh * 1.0
        evidence.append(RegimeEvidence(
            feature="higher_highs", value=hh,
            supports="BULL_TREND",
            description=f"Higher-high structure score {hh:.2f}"
        ))

    if persistence > 0.7 and roc > 0:
        scores["BULL_TREND"] += 0.5
        evidence.append(RegimeEvidence(
            feature="momentum_persistence", value=persistence,
            supports="BULL_TREND",
            description=f"Momentum persistence {persistence:.2f} in up direction"
        ))

    # ── BEAR_TREND ────────────────────────────────────────────────────────────
    if adx >= 20:
        di_bias = minus_di - plus_di
        if di_bias > 0:
            s = min(adx / 40, 1.0) * (di_bias / 30) * 3.0
            scores["BEAR_TREND"] += s
            evidence.append(RegimeEvidence(
                feature="adx+minus_di", value=di_bias,
                supports="BEAR_TREND",
                description=f"ADX {adx:.1f}, -DI leads by {di_bias:.1f}"
            ))

    if slope < -0.002:
        scores["BEAR_TREND"] += min(-slope / 0.01, 1.0) * 1.5
        evidence.append(RegimeEvidence(
            feature="trend_slope", value=slope,
            supports="BEAR_TREND",
            description=f"Negative trend slope {slope:.4f}"
        ))

    if hh < -0.5:
        scores["BEAR_TREND"] += abs(hh) * 1.0

    if persistence > 0.7 and roc < 0:
        scores["BEAR_TREND"] += 0.5

    # ── BREAKOUT ──────────────────────────────────────────────────────────────
    if vol_exp > 1.3:
        scores["BREAKOUT"] += (vol_exp - 1.0) * 2.0
        evidence.append(RegimeEvidence(
            feature="vol_expansion", value=vol_exp,
            supports="BREAKOUT",
            description=f"Volatility expansion {vol_exp:.2f}x — range breaking"
        ))

    if rel_vol > 1.4:
        scores["BREAKOUT"] += min((rel_vol - 1.0) / 2.0, 1.0) * 2.0
        evidence.append(RegimeEvidence(
            feature="rel_volume", value=rel_vol,
            supports="BREAKOUT",
            description=f"Relative volume {rel_vol:.2f}x — volume expanding"
        ))

    if range_comp < 0.5:
        scores["BREAKOUT"] += (1.0 - range_comp) * 1.5
        evidence.append(RegimeEvidence(
            feature="range_compression", value=range_comp,
            supports="BREAKOUT",
            description=f"Range compression {range_comp:.2f} — coiled, breakout likely"
        ))

    # ── RANGE ─────────────────────────────────────────────────────────────────
    if adx < 20:
        scores["RANGE"] += (20 - adx) / 20 * 2.0
        evidence.append(RegimeEvidence(
            feature="adx", value=adx,
            supports="RANGE",
            description=f"ADX {adx:.1f} below trend threshold"
        ))

    if 40 < rsi < 60:
        scores["RANGE"] += 1.0
        evidence.append(RegimeEvidence(
            feature="rsi", value=rsi,
            supports="RANGE",
            description=f"RSI {rsi:.1f} mid-band — no clear momentum"
        ))

    if abs(vwap_dist) < 0.005:
        scores["RANGE"] += 0.5
        evidence.append(RegimeEvidence(
            feature="vwap_distance", value=vwap_dist,
            supports="RANGE",
            description=f"Price hugging VWAP ({vwap_dist:.3%}) — equilibrium"
        ))

    # ── MEAN_REVERT ───────────────────────────────────────────────────────────
    if rsi < 32 and adx < 25:
        scores["MEAN_REVERT"] += (32 - rsi) / 32 * 3.0
        evidence.append(RegimeEvidence(
            feature="rsi", value=rsi,
            supports="MEAN_REVERT",
            description=f"RSI {rsi:.1f} oversold + weak trend — mean reversion candidate"
        ))

    if rsi > 68 and adx < 25:
        scores["MEAN_REVERT"] += (rsi - 68) / 32 * 3.0
        evidence.append(RegimeEvidence(
            feature="rsi", value=rsi,
            supports="MEAN_REVERT",
            description=f"RSI {rsi:.1f} overbought + weak trend — mean reversion candidate"
        ))

    if abs(vwap_dist) > 0.02 and adx < 20:
        scores["MEAN_REVERT"] += min(abs(vwap_dist) / 0.05, 1.0)

    return scores, evidence


def classify_regime_v2(bars: list[Bar]) -> RegimeResult:
    """
    Probabilistic regime classification.
    Returns RegimeResult with full probability distribution.
    """
    fv = extract_features(bars)
    return classify_regime_from_features(fv)


def classify_regime_from_features(fv: FeatureVector) -> RegimeResult:
    """Classify regime from pre-computed FeatureVector (avoids double computation)."""
    raw_scores, evidence = _score_regimes(fv)

    # Ensure all regimes have a base score (Laplace smoothing — prevents zero probs)
    for label in REGIME_LABELS:
        if raw_scores[label] == 0.0:
            raw_scores[label] = 0.01

    probs = _softmax(raw_scores)

    # Top regime
    top_label: RegimeLabel = max(probs, key=lambda k: probs[k])
    confidence = probs[top_label]

    # Human-readable notes
    notes_map = {
        "BULL_TREND": "Strong directional uptrend confirmed. Momentum/trend-follow strategies preferred.",
        "BEAR_TREND": "Confirmed downtrend. Short momentum or cash is preferred.",
        "RANGE": "No directional trend. Mean-reversion strategies most applicable.",
        "BREAKOUT": "Volume and volatility expansion underway. ORB / breakout strategies have edge.",
        "HIGH_VOL": "Elevated volatility. Widen stops; breakout fades common. Size down.",
        "LOW_VOL": "Compressed volatility. Potential energy building — watch for breakout trigger.",
        "MEAN_REVERT": "Overextended move without trend confirmation. Mean-reversion setup.",
        "STRESS": "Tail volatility — potential crisis/news event. Avoid new risk. Cash/hedge.",
    }

    vol = fv.realized_vol
    adx = fv.adx
    trend_strength = min(1.0, adx / 40)
    vol_pct = max(0.0, min(1.0, (vol - 0.08) / 0.28))

    return RegimeResult(
        label=top_label,
        probabilities=probs,
        confidence=confidence,
        adx=adx,
        realized_vol=vol,
        vol_percentile=vol_pct,
        trend_strength=trend_strength,
        notes=notes_map.get(top_label, ""),
        evidence=evidence,
        model_version=MODEL_VERSION,
    )


def regime_strategy_fit(strategy_id: str, regime_probs: dict[str, float]) -> float:
    """
    Compute regime fit score for a strategy using full probability distribution.
    Returns weighted average fit over all regimes.
    V2: uses probability weighting instead of hard label lookup.
    """
    # Historical fit scores: how well each strategy performs in each regime
    fit_table: dict[str, dict[str, float]] = {
        "ma_cross":  {
            "BULL_TREND": 1.0, "BEAR_TREND": 0.9, "BREAKOUT": 0.8,
            "RANGE": 0.3, "HIGH_VOL": 0.5, "LOW_VOL": 0.5,
            "MEAN_REVERT": 0.25, "STRESS": 0.1,
        },
        "vwap_rsi":  {
            "BULL_TREND": 0.9, "BEAR_TREND": 0.7, "BREAKOUT": 0.8,
            "RANGE": 0.4, "HIGH_VOL": 0.4, "LOW_VOL": 0.8,
            "MEAN_REVERT": 0.6, "STRESS": 0.15,
        },
        "orb":       {
            "BULL_TREND": 0.8, "BEAR_TREND": 0.8, "BREAKOUT": 1.0,
            "RANGE": 0.2, "HIGH_VOL": 0.75, "LOW_VOL": 0.3,
            "MEAN_REVERT": 0.2, "STRESS": 0.1,
        },
    }
    strategy_fits = fit_table.get(strategy_id, {label: 0.5 for label in REGIME_LABELS})

    # Weighted average fit
    total_fit = sum(regime_probs.get(label, 0.0) * strategy_fits.get(label, 0.5)
                    for label in REGIME_LABELS)
    return min(1.0, max(0.0, total_fit))
