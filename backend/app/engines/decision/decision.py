"""
backend/app/engines/decision/decision.py

Port of src/lib/aura/decision.ts
compute_decision() — the authoritative Python decision engine.
"""

from __future__ import annotations

from backend.app.engines.decision.indicators import compute_indicators
from backend.app.engines.decision.regime import classify_regime, regime_fits
from backend.app.engines.decision.similarity import similar_setups
from backend.app.engines.decision.strategies import run_all_strategies
from backend.app.schemas.types import (
    Bar,
    COST_VERSION,
    DATASET_VERSION,
    Decision,
    DecisionLineage,
    Evidence,
    FEATURE_VERSION,
    Learning,
    MODEL_VERSION,
    Quote,
    Regime,
    SimilarMatch,
    StrategyOutput,
)


def _dir_probs(
    sig: StrategyOutput,
    regime: Regime,
    similar: SimilarMatch,
) -> dict[str, float]:
    up = 0.33
    down = 0.33
    if sig.action == "BUY":
        up = 0.45 + sig.confidence * 0.25
    if sig.action == "SELL":
        down = 0.45 + sig.confidence * 0.25
    if regime.label == "BULL_TREND":
        up += 0.06
    if regime.label == "BEAR_TREND":
        down += 0.06
    if similar.n >= 12:
        up = up * 0.7 + similar.winRate * 0.3
        down = down * 0.7 + (1 - similar.winRate) * 0.3
    s = up + down + 0.2
    return {"up": up / s, "down": down / s, "neutral": 0.2 / s}


def _pick_best(outputs: list[StrategyOutput], regime_label: str) -> StrategyOutput:
    scored = []
    for o in outputs:
        fit = regime_fits(o.strategyId, regime_label)
        actionable = 1.0 if o.action in ("BUY", "SELL") else 0.4
        scored.append((o, o.confidence * fit * actionable))
    scored.sort(key=lambda x: -x[1])
    return scored[0][0]


def compute_decision(
    symbol: str,
    bars: list[Bar],
    quote: Quote,
    learnings: list[Learning],
) -> Decision:
    """
    Authoritative Python decision engine.
    Parameter names/shapes match TypeScript decideSymbol() as closely as practical.
    """
    live = list(bars)
    last = live[-1]
    live[-1] = Bar(
        t=last.t,
        o=last.o,
        h=max(last.h, quote.ltp),
        l=min(last.l, quote.ltp),
        c=quote.ltp,
        v=last.v,
    )

    regime = classify_regime(live)
    outputs = run_all_strategies(live)
    strategy = _pick_best(outputs, regime.label)
    similar = similar_setups(bars, 5, symbol)
    ind = compute_indicators(live)
    fit = regime_fits(strategy.strategyId, regime.label)

    reasons: list[Evidence] = []
    contradictions: list[Evidence] = []

    reasons.append(Evidence(kind="support", text=strategy.reason))
    reasons.append(Evidence(
        kind="support",
        text=f"Regime: {regime.label.replace('_', ' ').lower()}. {regime.notes}",
    ))

    if similar.n >= 8:
        txt = (
            f"{similar.n} similar setups · win rate {similar.winRate * 100:.0f}% · "
            f"avg {similar.avgReturn * 100:.2f}% over ~{similar.avgHoldBars}d"
        )
        if similar.winRate >= 0.5:
            reasons.append(Evidence(kind="support", text=txt))
        else:
            contradictions.append(Evidence(kind="contradict", text=txt))
    else:
        contradictions.append(Evidence(
            kind="contradict",
            text=f"Only {similar.n} historical neighbors — sample is too small to lean on.",
        ))

    if fit < 0.5:
        contradictions.append(Evidence(
            kind="contradict",
            text=f"Strategy family is a poor match for {regime.label.replace('_', ' ').lower()}.",
        ))

    if ind.realizedVol > 0.28:
        contradictions.append(Evidence(kind="contradict", text="Elevated realized vol — adverse excursion risk is high."))

    if strategy.action == "BUY" and ind.rsi > 72:
        contradictions.append(Evidence(kind="contradict", text=f"RSI {ind.rsi:.0f} is stretched for a fresh long."))

    if strategy.action == "SELL" and ind.rsi < 28:
        contradictions.append(Evidence(kind="contradict", text=f"RSI {ind.rsi:.0f} is stretched for a fresh short."))

    action = strategy.action
    confidence = strategy.confidence * (0.65 + 0.35 * fit)

    if similar.n >= 12 and similar.winRate < 0.4 and action in ("BUY", "SELL"):
        action = "SKIP"
        confidence *= 0.5
        contradictions.append(Evidence(
            kind="contradict",
            text="Similarity engine: this setup historically underperformed. SKIP.",
        ))

    if regime.label == "STRESS" and action != "HOLD":
        action = "SKIP"
        contradictions.append(Evidence(kind="contradict", text="Stress regime — risk engine prefers no new risk."))

    probs = _dir_probs(strategy, regime, similar)

    rr = None
    if strategy.entry is not None and strategy.stop is not None and strategy.target is not None:
        denom = abs(strategy.entry - strategy.stop)
        if denom < 1e-9:
            denom = 1e-9
        rr = abs(strategy.target - strategy.entry) / denom

    risk_level: str = "MODERATE"
    if action == "SKIP":
        risk_level = "HIGH"
    elif confidence > 0.7 and (rr or 0) >= 1.8 and similar.winRate >= 0.52:
        risk_level = "LOW"
    elif ind.realizedVol > 0.24 or fit < 0.5:
        risk_level = "HIGH"

    return Decision(
        id=f"{symbol}-{strategy.strategyId}-{strategy.version}",
        symbol=symbol,
        ts=quote.ts,
        action=action,
        probabilityUp=probs["up"],
        probabilityDown=probs["down"],
        probabilityNeutral=probs["neutral"],
        confidence=confidence,
        risk=risk_level,
        expectedRR=rr,
        entry=strategy.entry,
        stop=strategy.stop,
        target=strategy.target,
        invalidation=strategy.invalidation,
        reasons=reasons,
        contradictions=contradictions,
        strategy=strategy,
        regime=regime,
        similar=similar,
        riskReasons=[],
        lineage=DecisionLineage(
            strategyVersion=f"{strategy.strategyId}@{strategy.version}",
            modelVersion=MODEL_VERSION,
            featureVersion=FEATURE_VERSION,
            datasetVersion=DATASET_VERSION,
            costVersion=COST_VERSION,
        ),
    )


def decide_universe(quotes: dict[str, Quote], learnings: list[Learning] = None) -> list[Decision]:
    from backend.app.data.simulator import bars_of
    learnings = learnings or []
    out: list[Decision] = []
    for symbol, quote in quotes.items():
        bars = bars_of(symbol, "1D")
        out.append(compute_decision(symbol, bars, quote, learnings))

    def rank(d: Decision) -> float:
        base = 2.0 if d.action in ("BUY", "SELL") else (1.0 if d.action == "HOLD" else 0.0)
        return base * d.confidence

    out.sort(key=lambda d: -rank(d))
    return out
