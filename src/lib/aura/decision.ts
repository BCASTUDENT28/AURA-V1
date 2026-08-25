import { computeIndicators } from "./indicators";
import { getInstrument } from "./instruments";
import { barsOf } from "./market";
import { classifyRegime, regimeFits } from "./regime";
import { similarSetups } from "./similarity";
import { runAllStrategies } from "./strategies";
import type { Decision, Evidence, Quote, Regime, StrategyOutput } from "./types";
import { DATASET_VERSION, FEATURE_VERSION, MODEL_VERSION, COST_VERSION } from "./types";

function dirProbs(sig: StrategyOutput, regime: Regime, similar: { n: number; winRate: number; avgReturn: number }): {
  up: number;
  down: number;
  neutral: number;
} {
  let up = 0.33;
  let down = 0.33;
  if (sig.action === "BUY") up = 0.45 + sig.confidence * 0.25;
  if (sig.action === "SELL") down = 0.45 + sig.confidence * 0.25;
  if (regime.label === "BULL_TREND") up += 0.06;
  if (regime.label === "BEAR_TREND") down += 0.06;
  if (similar.n >= 12) {
    up = up * 0.7 + similar.winRate * 0.3;
    down = down * 0.7 + (1 - similar.winRate) * 0.3;
  }
  const s = up + down + 0.2;
  return { up: up / s, down: down / s, neutral: 0.2 / s };
}

function pickBest(outputs: StrategyOutput[], regimeLabel: string): StrategyOutput {
  const scored = outputs.map((o) => {
    const fit = regimeFits(o.strategyId, regimeLabel as never);
    const actionable = o.action === "BUY" || o.action === "SELL" ? 1 : 0.4;
    return { o, s: o.confidence * fit * actionable };
  });
  scored.sort((a, b) => b.s - a.s);
  return scored[0]!.o;
}

export function decideSymbol(symbol: string, quote: Quote): Decision {
  const daily = barsOf(symbol, "1D");
  const live = daily.slice();
  const last = live[live.length - 1]!;
  live[live.length - 1] = { ...last, c: quote.ltp, h: Math.max(last.h, quote.ltp), l: Math.min(last.l, quote.ltp) };
  const regime = classifyRegime(live);
  const outputs = runAllStrategies(live);
  const strategy = pickBest(outputs, regime.label);
  const similar = similarSetups(daily, 5, symbol);
  const ind = computeIndicators(live);
  const fit = regimeFits(strategy.strategyId, regime.label);
  const reasons: Evidence[] = [];
  const contradictions: Evidence[] = [];

  reasons.push({ kind: "support", text: strategy.reason });
  reasons.push({ kind: "support", text: `Regime: ${regime.label.replaceAll("_", " ").toLowerCase()}. ${regime.notes}` });
  if (similar.n >= 8) {
    const txt = `${similar.n} similar setups · win rate ${(similar.winRate * 100).toFixed(0)}% · avg ${(similar.avgReturn * 100).toFixed(2)}% over ~${similar.avgHoldBars}d`;
    (similar.winRate >= 0.5 ? reasons : contradictions).push({
      kind: similar.winRate >= 0.5 ? "support" : "contradict",
      text: txt,
    });
  } else {
    contradictions.push({
      kind: "contradict",
      text: `Only ${similar.n} historical neighbors — sample is too small to lean on.`,
    });
  }
  if (fit < 0.5) {
    contradictions.push({
      kind: "contradict",
      text: `Strategy family is a poor match for ${regime.label.replaceAll("_", " ").toLowerCase()}.`,
    });
  }
  if (ind.realizedVol > 0.28) {
    contradictions.push({ kind: "contradict", text: "Elevated realized vol — adverse excursion risk is high." });
  }
  if (strategy.action === "BUY" && ind.rsi > 72) {
    contradictions.push({ kind: "contradict", text: `RSI ${ind.rsi.toFixed(0)} is stretched for a fresh long.` });
  }
  if (strategy.action === "SELL" && ind.rsi < 28) {
    contradictions.push({ kind: "contradict", text: `RSI ${ind.rsi.toFixed(0)} is stretched for a fresh short.` });
  }

  let action = strategy.action;
  let confidence = strategy.confidence * (0.65 + 0.35 * fit);
  if (similar.n >= 12 && similar.winRate < 0.4 && (action === "BUY" || action === "SELL")) {
    action = "SKIP";
    confidence *= 0.5;
    contradictions.push({
      kind: "contradict",
      text: "Similarity engine: this setup historically underperformed. SKIP.",
    });
  }
  if (regime.label === "STRESS" && action !== "HOLD") {
    action = "SKIP";
    contradictions.push({ kind: "contradict", text: "Stress regime — risk engine prefers no new risk." });
  }

  const probs = dirProbs(strategy, regime, similar);
  const rr =
    strategy.entry && strategy.stop && strategy.target
      ? Math.abs(strategy.target - strategy.entry) / Math.max(1e-9, Math.abs(strategy.entry - strategy.stop))
      : null;
  let risk: Decision["risk"] = "MODERATE";
  if (action === "SKIP") risk = "HIGH";
  else if (confidence > 0.7 && (rr ?? 0) >= 1.8 && similar.winRate >= 0.52) risk = "LOW";
  else if (ind.realizedVol > 0.24 || fit < 0.5) risk = "HIGH";

  const inst = getInstrument(symbol);
  return {
    id: `${symbol}-${strategy.strategyId}-${strategy.version}`,
    symbol,
    ts: quote.ts,
    action,
    probabilityUp: probs.up,
    probabilityDown: probs.down,
    probabilityNeutral: probs.neutral,
    confidence,
    risk,
    expectedRR: rr,
    entry: strategy.entry,
    stop: strategy.stop,
    target: strategy.target,
    invalidation: strategy.invalidation,
    reasons,
    contradictions,
    strategy,
    regime,
    similar,
    riskReasons: [],
    lineage: {
      strategyVersion: `${strategy.strategyId}@${strategy.version}`,
      modelVersion: MODEL_VERSION,
      featureVersion: FEATURE_VERSION,
      datasetVersion: DATASET_VERSION,
      costVersion: COST_VERSION,
    },
  };
}

export function decideUniverse(quotes: Record<string, Quote>): Decision[] {
  const out: Decision[] = [];
  for (const symbol of Object.keys(quotes)) {
    if (getInstrument(symbol).kind === "index") {
      // still produce a regime-led decision for the index
    }
    out.push(decideSymbol(symbol, quotes[symbol]!));
  }
  out.sort((a, b) => {
    const rank = (x: Decision) =>
      (x.action === "BUY" || x.action === "SELL" ? 2 : x.action === "HOLD" ? 1 : 0) * x.confidence;
    return rank(b) - rank(a);
  });
  return out;
}
