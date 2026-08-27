"""
backend/app/engines/ensemble/decision_engine.py

AURA V2 Ensemble Decision Engine
=================================

Combines:
  1. Strategy signals (3 strategies, each with confidence + regime_fit)
  2. Regime probabilities (V2 probabilistic classifier)
  3. Feature evidence (feature vector)
  4. Historical similarity (cosine vector store)
  5. Risk state (snapshot_risk)

Produces a DecisionExplanation with:
  - final_action: BUY | SELL | HOLD | NO_TRADE
  - NO_TRADE is a first-class action (used when evidence is weak/contradictory)
  - confidence [0, 1]
  - expected_edge_bps (expected basis points of edge)
  - expected_R (risk-reward ratio)
  - strategy_votes (all strategy signals with weights)
  - rejection_reasons (why NO_TRADE was chosen)
  - full explainability for frontend

Expected Value Engine (Phase 7):
  - probability_of_win / probability_of_loss
  - average_win / average_loss from similarity history
  - expected_value = P(win) × avg_win - P(loss) × avg_loss
  - Rejects trades where net_expected_value < MIN_EDGE_BPS

Position Sizing Engine (Phase 8):
  - Fixed-risk per trade (% of equity)
  - ATR-based stop distance
  - Correlation-aware exposure cap
  - Returns recommended_qty
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from backend.app.engines.decision.strategies import run_all_strategies
from backend.app.engines.regime.regime_v2 import (
    classify_regime_from_features,
    regime_strategy_fit,
    RegimeResult,
)
from backend.app.features.engine import FeatureVector, extract_features
from backend.app.schemas.types import Bar, Quote, StrategyOutput

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

MIN_EDGE_BPS = 15.0          # Minimum expected edge to allow a trade
MIN_CONFIDENCE = 0.35        # Minimum strategy confidence to consider
MIN_REGIME_FIT = 0.30        # Minimum regime fit to allow
MIN_SIMILAR_SAMPLES = 8      # Minimum historical analogues for similarity weight
RISK_PER_TRADE_PCT = 0.01    # 1% of equity per trade (default)
MAX_POSITION_PCT = 0.10      # Max 10% of equity in one position
SLIPPAGE_BPS = 5.0           # Estimated one-way slippage


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StrategyVote:
    strategy_id: str
    action: str
    confidence: float
    regime_fit: float
    weight: float           # normalized weight in ensemble
    entry: Optional[float]
    stop: Optional[float]
    target: Optional[float]
    reason: str
    invalidation: str
    feature_evidence: list[str] = field(default_factory=list)


@dataclass
class ExpectedValueEstimate:
    """
    Expected value calculation for a candidate trade.
    All values are in basis points (bps) relative to entry price.
    """
    probability_win: float
    probability_loss: float
    avg_win_bps: float
    avg_loss_bps: float
    expected_value_bps: float
    estimated_cost_bps: float
    estimated_slippage_bps: float
    net_expected_value_bps: float
    sample_size: int
    calibrated: bool = False   # True only if based on sufficient historical data

    @property
    def is_positive_ev(self) -> bool:
        return self.net_expected_value_bps >= MIN_EDGE_BPS


@dataclass
class PositionSize:
    """Recommended position size from risk-adjusted sizing."""
    recommended_qty: int
    risk_per_trade_pct: float
    stop_distance: float       # in price units
    stop_distance_pct: float   # as % of entry
    max_loss_amount: float     # in currency
    equity_used_pct: float     # what % of equity this occupies
    sizing_method: str         # "atr_based" | "fixed_risk" | "capped"


@dataclass
class DecisionExplanation:
    """
    Full explainability output from the ensemble decision engine.
    Every field has a purpose — no decorative data.
    """
    # Core decision
    final_action: str                      # BUY | SELL | HOLD | NO_TRADE
    confidence: float                      # [0, 1] aggregate confidence
    expected_edge_bps: float               # net expected edge in basis points
    expected_R: Optional[float]            # risk-reward ratio
    regime_label: str
    regime_confidence: float               # probability of top regime

    # Votes
    strategy_votes: list[StrategyVote]
    winning_strategy: Optional[str]

    # Evidence
    reasons: list[str]                     # why this action
    contradictions: list[str]              # evidence against
    rejection_reasons: list[str]           # why NO_TRADE if applicable

    # Probabilities
    probability_up: float
    probability_down: float
    probability_neutral: float

    # Trade parameters (None if NO_TRADE)
    entry: Optional[float]
    stop: Optional[float]
    target: Optional[float]
    invalidation: str

    # Expected value
    expected_value: Optional[ExpectedValueEstimate]

    # Position sizing
    position_size: Optional[PositionSize]

    # Risk
    risk_level: str                        # LOW | MODERATE | HIGH | BLOCKED
    risk_reasons: list[str]

    # Historical support
    similar_n: int
    similar_win_rate: float
    historical_support: str

    # Metadata
    model_version: str
    feature_version: str
    strategy_version: str = "v1"


# ─────────────────────────────────────────────────────────────────────────────
# Expected Value Engine
# ─────────────────────────────────────────────────────────────────────────────

def compute_expected_value(
    strategy_output: StrategyOutput,
    regime_result: RegimeResult,
    similar_n: int,
    similar_win_rate: float,
    similar_avg_return: float,
    similar_avg_mae: float,
    entry_px: float,
) -> ExpectedValueEstimate:
    """
    Estimate expected value for a candidate trade.

    When similar_n >= MIN_SIMILAR_SAMPLES, uses historical win rate and returns.
    When similar_n < MIN_SIMILAR_SAMPLES, falls back to strategy confidence estimate.
    Never fabricates ML performance — explicitly marks calibration status.
    """
    # ── Determine P(win) and P(loss) ─────────────────────────────────────────
    calibrated = similar_n >= MIN_SIMILAR_SAMPLES

    if calibrated:
        prob_win = similar_win_rate
        prob_loss = 1.0 - similar_win_rate
    else:
        # Use strategy confidence as directional probability estimate
        # Explicitly uncalibrated — treated conservatively
        base_prob = 0.45 + strategy_output.confidence * 0.2  # max ~0.65
        regime_boost = regime_strategy_fit(strategy_output.strategyId, regime_result.probabilities)
        prob_win = min(0.70, base_prob * regime_boost)
        prob_loss = 1.0 - prob_win

    # ── Estimate average win / loss in BPS ───────────────────────────────────
    if calibrated and similar_avg_return != 0:
        # Scale from fraction to BPS
        avg_win_bps = max(0, similar_avg_return * 10_000 * 1.2)  # wins > avg
        avg_loss_bps = abs(similar_avg_mae * 10_000 * 0.8)       # losses ~ MAE
    else:
        # Infer from R-ratio
        entry = strategy_output.entry or entry_px
        stop = strategy_output.stop
        target = strategy_output.target
        if stop and target and entry:
            risk_bps = abs(entry - stop) / entry * 10_000
            reward_bps = abs(target - entry) / entry * 10_000
        else:
            risk_bps = 100.0   # assume 1% stop
            reward_bps = 200.0  # assume 2% target (2R)
        avg_win_bps = reward_bps
        avg_loss_bps = risk_bps

    # ── Expected Value ────────────────────────────────────────────────────────
    ev_bps = prob_win * avg_win_bps - prob_loss * avg_loss_bps
    cost_bps = 10.0    # ~10 bps all-in cost (STT + exchange + brokerage)
    slip_bps = SLIPPAGE_BPS
    net_ev_bps = ev_bps - cost_bps - slip_bps

    return ExpectedValueEstimate(
        probability_win=round(prob_win, 4),
        probability_loss=round(prob_loss, 4),
        avg_win_bps=round(avg_win_bps, 2),
        avg_loss_bps=round(avg_loss_bps, 2),
        expected_value_bps=round(ev_bps, 2),
        estimated_cost_bps=round(cost_bps, 2),
        estimated_slippage_bps=round(slip_bps, 2),
        net_expected_value_bps=round(net_ev_bps, 2),
        sample_size=similar_n,
        calibrated=calibrated,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Position Sizing Engine
# ─────────────────────────────────────────────────────────────────────────────

def compute_position_size(
    entry_px: float,
    stop_px: float,
    account_equity: float,
    atr: float,
    risk_per_trade_pct: float = RISK_PER_TRADE_PCT,
    max_position_pct: float = MAX_POSITION_PCT,
    open_positions: int = 0,
    max_positions: int = 5,
) -> PositionSize:
    """
    ATR-adjusted, fixed-risk position sizing.

    Formula:
      stop_distance = |entry - stop|
      risk_capital = equity × risk_per_trade_pct
      qty = risk_capital / stop_distance

    Caps:
      - Max position_value = equity × max_position_pct
      - Reduced if open_positions approaching max_positions
    """
    stop_distance = abs(entry_px - stop_px)
    if stop_distance < 0.01:
        stop_distance = atr * 1.5  # fallback: 1.5×ATR stop

    risk_capital = account_equity * risk_per_trade_pct

    # Exposure adjustment: reduce sizing as positions fill up
    position_factor = 1.0 - (open_positions / max(max_positions, 1)) * 0.3
    adjusted_risk = risk_capital * position_factor

    qty_float = adjusted_risk / stop_distance
    qty = max(1, int(qty_float))

    # Cap by max position size
    max_value = account_equity * max_position_pct
    max_qty = max(1, int(max_value / entry_px))
    qty = min(qty, max_qty)

    position_value = qty * entry_px
    equity_used_pct = position_value / account_equity if account_equity else 0.0
    stop_dist_pct = stop_distance / entry_px if entry_px else 0.0

    return PositionSize(
        recommended_qty=qty,
        risk_per_trade_pct=risk_per_trade_pct,
        stop_distance=round(stop_distance, 2),
        stop_distance_pct=round(stop_dist_pct, 4),
        max_loss_amount=round(qty * stop_distance, 2),
        equity_used_pct=round(equity_used_pct, 4),
        sizing_method="atr_based" if stop_distance == atr * 1.5 else "fixed_risk",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Ensemble Decision Engine
# ─────────────────────────────────────────────────────────────────────────────

def _compute_weighted_votes(
    strategy_outputs: list[StrategyOutput],
    regime_result: RegimeResult,
) -> list[StrategyVote]:
    """
    Compute weighted votes for all strategies.
    Weight = confidence × regime_fit
    Normalized so weights sum to 1.0.
    """
    votes: list[StrategyVote] = []
    for s in strategy_outputs:
        fit = regime_strategy_fit(s.strategyId, regime_result.probabilities)
        raw_weight = s.confidence * fit
        votes.append(StrategyVote(
            strategy_id=s.strategyId,
            action=s.action,
            confidence=s.confidence,
            regime_fit=fit,
            weight=raw_weight,  # normalized below
            entry=s.entry,
            stop=s.stop,
            target=s.target,
            reason=s.reason,
            invalidation=s.invalidation,
            feature_evidence=list(s.featureEvidence),
        ))

    total_weight = sum(v.weight for v in votes) or 1.0
    for v in votes:
        v.weight = v.weight / total_weight

    return sorted(votes, key=lambda v: -v.weight)


def _aggregate_action(
    votes: list[StrategyVote],
    regime_result: RegimeResult,
) -> tuple[str, float]:
    """
    Aggregate strategy votes into a final action using weighted voting.
    Returns (action, confidence).
    """
    action_scores: dict[str, float] = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0, "NO_TRADE": 0.0}

    for v in votes:
        action = v.action
        if action in ("SKIP",):
            action = "NO_TRADE"
        if action in action_scores:
            action_scores[action] += v.weight * v.confidence

    # Stress regime forces NO_TRADE
    if regime_result.probabilities.get("STRESS", 0) > 0.45:
        action_scores["NO_TRADE"] += 0.5

    best_action = max(action_scores, key=lambda k: action_scores[k])
    confidence = action_scores[best_action]

    return best_action, min(1.0, confidence)


def _compute_direction_probs(
    action: str,
    confidence: float,
    regime_result: RegimeResult,
    similar_win_rate: float,
    similar_n: int,
) -> tuple[float, float, float]:
    """
    Compute P(up), P(down), P(neutral) from all evidence.
    Returns (p_up, p_down, p_neutral).
    """
    # Base from action
    if action == "BUY":
        p_up = 0.40 + confidence * 0.25
    elif action == "SELL":
        p_up = 0.35 - confidence * 0.20
    else:
        p_up = 0.33

    # Regime boost
    bull_prob = regime_result.probabilities.get("BULL_TREND", 0)
    bear_prob = regime_result.probabilities.get("BEAR_TREND", 0)
    p_up += bull_prob * 0.08 - bear_prob * 0.08

    # Similarity adjustment (only if sufficient samples)
    if similar_n >= MIN_SIMILAR_SAMPLES:
        p_up = p_up * 0.7 + similar_win_rate * 0.3

    p_up = max(0.05, min(0.85, p_up))
    p_down = max(0.05, min(0.85, 1.0 - p_up - 0.1))
    p_neutral = max(0.0, 1.0 - p_up - p_down)

    return round(p_up, 4), round(p_down, 4), round(p_neutral, 4)


def compute_ensemble_decision(
    symbol: str,
    bars: list[Bar],
    quote: Quote,
    account_equity: float = 1_000_000.0,
    similar_n: int = 0,
    similar_win_rate: float = 0.5,
    similar_avg_return: float = 0.0,
    similar_avg_mae: float = 0.0,
    open_positions: int = 0,
) -> DecisionExplanation:
    """
    Main entry point for ensemble decision making.

    Returns a DecisionExplanation with full explainability.
    NO_TRADE is returned when:
      - No strategy agrees
      - Expected value is negative
      - Regime fit is poor for all strategies
      - Stress regime detected
      - Insufficient evidence (sample too small + confidence too low)
    """
    from backend.app.schemas.types import MODEL_VERSION, FEATURE_VERSION

    # 1. Build feature vector
    fv = extract_features(bars)

    # 2. Get regime probabilities
    regime_result = classify_regime_from_features(fv)

    # 3. Run all strategies
    strategy_outputs = run_all_strategies(bars)

    # 4. Compute weighted votes
    votes = _compute_weighted_votes(strategy_outputs, regime_result)

    # 5. Aggregate action
    action, confidence = _aggregate_action(votes, regime_result)

    # 6. Identify winning strategy (highest weight)
    best_vote = votes[0] if votes else None
    winning_strategy = best_vote.strategy_id if best_vote else None

    # 7. Compute expected value
    best_strategy_output = next(
        (s for s in strategy_outputs if s.strategyId == winning_strategy),
        strategy_outputs[0] if strategy_outputs else None
    )

    rejection_reasons: list[str] = []
    ev: Optional[ExpectedValueEstimate] = None

    if best_strategy_output and action in ("BUY", "SELL"):
        ev = compute_expected_value(
            strategy_output=best_strategy_output,
            regime_result=regime_result,
            similar_n=similar_n,
            similar_win_rate=similar_win_rate,
            similar_avg_return=similar_avg_return,
            similar_avg_mae=similar_avg_mae,
            entry_px=quote.ltp,
        )

        if not ev.is_positive_ev:
            rejection_reasons.append(
                f"Net expected value {ev.net_expected_value_bps:.1f} bps < {MIN_EDGE_BPS} bps threshold"
            )
            action = "NO_TRADE"

    # 8. Check minimum confidence and regime fit
    if action in ("BUY", "SELL"):
        if confidence < MIN_CONFIDENCE:
            rejection_reasons.append(f"Confidence {confidence:.2f} < {MIN_CONFIDENCE} minimum")
            action = "NO_TRADE"

        if best_vote and best_vote.regime_fit < MIN_REGIME_FIT:
            rejection_reasons.append(
                f"Best strategy regime fit {best_vote.regime_fit:.2f} < {MIN_REGIME_FIT} minimum"
            )
            action = "NO_TRADE"

    # 9. Compute position sizing (only if trading)
    position_size: Optional[PositionSize] = None
    entry = best_vote.entry if best_vote else None
    stop = best_vote.stop if best_vote else None
    target = best_vote.target if best_vote else None
    invalidation = best_vote.invalidation if best_vote else ""

    if action in ("BUY", "SELL") and entry and stop:
        position_size = compute_position_size(
            entry_px=entry,
            stop_px=stop,
            account_equity=account_equity,
            atr=fv.atr,
            open_positions=open_positions,
        )

    # 10. Direction probabilities
    p_up, p_down, p_neutral = _compute_direction_probs(
        action, confidence, regime_result, similar_win_rate, similar_n
    )

    # 11. Expected R
    expected_R: Optional[float] = None
    if entry and stop and target:
        denom = abs(entry - stop)
        if denom > 1e-9:
            expected_R = round(abs(target - entry) / denom, 2)

    # 12. Risk level
    risk_reasons: list[str] = []
    if action == "NO_TRADE":
        risk_level = "BLOCKED"
    elif confidence > 0.68 and (expected_R or 0) >= 1.8 and ev and ev.probability_win >= 0.52:
        risk_level = "LOW"
    elif fv.realized_vol > 0.24 or (best_vote and best_vote.regime_fit < 0.5):
        risk_level = "HIGH"
        if fv.realized_vol > 0.24:
            risk_reasons.append(f"Elevated realized vol {fv.realized_vol:.1%}")
    else:
        risk_level = "MODERATE"

    # 13. Reasons and contradictions
    reasons: list[str] = []
    contradictions: list[str] = []

    if best_vote:
        reasons.append(best_vote.reason)
        reasons.extend(best_vote.feature_evidence)

    reasons.append(
        f"Regime: {regime_result.label} (confidence {regime_result.confidence:.0%})"
    )

    if similar_n >= MIN_SIMILAR_SAMPLES:
        sim_txt = f"{similar_n} similar setups: {similar_win_rate:.0%} win rate, avg return {similar_avg_return:.2%}"
        if similar_win_rate >= 0.5:
            reasons.append(sim_txt)
        else:
            contradictions.append(sim_txt)
    else:
        contradictions.append(f"Only {similar_n} historical analogues — insufficient for similarity evidence")

    if fv.realized_vol > 0.28:
        contradictions.append(f"Elevated realized vol {fv.realized_vol:.1%} — adverse excursion risk high")

    if best_vote and best_vote.regime_fit < 0.5:
        contradictions.append(f"Strategy {best_vote.strategy_id} poor fit for {regime_result.label} ({best_vote.regime_fit:.2f})")

    # RSI extremes
    if action == "BUY" and fv.rsi > 72:
        contradictions.append(f"RSI {fv.rsi:.0f} stretched — late long entry")
    if action == "SELL" and fv.rsi < 28:
        contradictions.append(f"RSI {fv.rsi:.0f} stretched — late short entry")

    edge_bps = ev.net_expected_value_bps if ev else 0.0

    return DecisionExplanation(
        final_action=action,
        confidence=round(confidence, 4),
        expected_edge_bps=round(edge_bps, 2),
        expected_R=expected_R,
        regime_label=regime_result.label,
        regime_confidence=round(regime_result.confidence, 4),
        strategy_votes=votes,
        winning_strategy=winning_strategy,
        reasons=reasons,
        contradictions=contradictions,
        rejection_reasons=rejection_reasons,
        probability_up=p_up,
        probability_down=p_down,
        probability_neutral=p_neutral,
        entry=entry,
        stop=stop,
        target=target,
        invalidation=invalidation,
        expected_value=ev,
        position_size=position_size,
        risk_level=risk_level,
        risk_reasons=risk_reasons,
        similar_n=similar_n,
        similar_win_rate=similar_win_rate,
        historical_support=f"{similar_n} analogues, {similar_win_rate:.0%} historical win rate" if similar_n > 0 else "No historical analogues",
        model_version="ensemble-v2",
        feature_version=fv.feature_version,
    )
