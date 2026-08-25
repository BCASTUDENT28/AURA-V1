import { computeIndicators } from "./indicators";
import { classifyRegime } from "./regime";
import type { Bar, StrategyConfig, StrategyOutput } from "./types";

export interface StrategyDef {
  id: string;
  name: string;
  version: string;
  family: string;
  summary: string;
  defaults: StrategyConfig;
  params: { key: string; label: string; min: number; max: number; step: number }[];
  run: (bars: Bar[], cfg: StrategyConfig) => StrategyOutput;
}

function base(
  id: string,
  version: string,
  action: StrategyOutput["action"],
  extra: Partial<StrategyOutput>,
): StrategyOutput {
  return {
    strategyId: id,
    version,
    action,
    entry: extra.entry ?? null,
    stop: extra.stop ?? null,
    target: extra.target ?? null,
    confidence: extra.confidence ?? 0.5,
    reason: extra.reason ?? "",
    invalidation: extra.invalidation ?? "",
    metadata: extra.metadata ?? {},
  };
}

function maCross(bars: Bar[], cfg: StrategyConfig): StrategyOutput {
  const fastN = cfg.fast ?? 9;
  const slowN = cfg.slow ?? 21;
  const slPct = cfg.slPct ?? 0.01;
  const rr = cfg.rr ?? 2;
  const ind = computeIndicators(bars);
  const px = bars[bars.length - 1]!.c;
  const prev = computeIndicators(bars.slice(0, -1));
  const crossedUp = prev.smaFast <= prev.smaSlow && ind.smaFast > ind.smaSlow;
  const crossedDn = prev.smaFast >= prev.smaSlow && ind.smaFast < ind.smaSlow;
  const alignedUp = ind.smaFast > ind.smaSlow && ind.ema9 > ind.ema21;
  const alignedDn = ind.smaFast < ind.smaSlow && ind.ema9 < ind.ema21;

  if (ind.adx < 15) {
    return base("ma_cross", "v1", "SKIP", {
      confidence: 0.35,
      reason: `ADX ${ind.adx.toFixed(1)} is below 15 — crossover in a dead trend is noise.`,
      invalidation: "Wait for ADX > 18 before acting on a cross.",
      metadata: { adx: ind.adx, fast: ind.smaFast, slow: ind.smaSlow },
    });
  }
  if (crossedUp || (alignedUp && ind.rsi > 52 && ind.rsi < 72)) {
    const stop = px * (1 - slPct);
    return base("ma_cross", "v1", "BUY", {
      entry: px,
      stop,
      target: px + (px - stop) * rr,
      confidence: Math.min(0.82, 0.5 + ind.adx / 80 + (crossedUp ? 0.1 : 0)),
      reason: crossedUp
        ? `SMA ${fastN} crossed above SMA ${slowN} with ADX ${ind.adx.toFixed(1)}.`
        : `Fast SMA remains above slow; RSI ${ind.rsi.toFixed(0)} supports continuation.`,
      invalidation: `Close back below SMA ${slowN} or stop at ${stop.toFixed(2)}.`,
      metadata: { fast: fastN, slow: slowN, adx: ind.adx, rsi: ind.rsi },
    });
  }
  if (crossedDn || (alignedDn && ind.rsi < 48 && ind.rsi > 28)) {
    const stop = px * (1 + slPct);
    return base("ma_cross", "v1", "SELL", {
      entry: px,
      stop,
      target: px - (stop - px) * rr,
      confidence: Math.min(0.8, 0.5 + ind.adx / 80 + (crossedDn ? 0.1 : 0)),
      reason: crossedDn
        ? `SMA ${fastN} crossed below SMA ${slowN} with ADX ${ind.adx.toFixed(1)}.`
        : `Fast SMA remains below slow; RSI ${ind.rsi.toFixed(0)} supports downside.`,
      invalidation: `Close back above SMA ${slowN} or stop at ${stop.toFixed(2)}.`,
      metadata: { fast: fastN, slow: slowN, adx: ind.adx, rsi: ind.rsi },
    });
  }
  return base("ma_cross", "v1", "HOLD", {
    confidence: 0.45,
    reason: "No fresh cross and RSI is mid-range. Stand aside.",
    invalidation: "A 9/21 cross with ADX > 18.",
    metadata: { rsi: ind.rsi, adx: ind.adx },
  });
}

function vwapRsi(bars: Bar[], cfg: StrategyConfig): StrategyOutput {
  const rsiBuy = cfg.rsiBuy ?? 55;
  const rsiSell = cfg.rsiSell ?? 45;
  const slPct = cfg.slPct ?? 0.01;
  const rr = cfg.rr ?? 2;
  const ind = computeIndicators(bars);
  const px = bars[bars.length - 1]!.c;
  const above = px > ind.vwap;
  const volOk = ind.relVolume >= 1.1;

  if (above && ind.rsi >= rsiBuy && ind.rsi <= 72 && volOk) {
    const stop = Math.min(px * (1 - slPct), ind.vwap * 0.997);
    return base("vwap_rsi", "v1", "BUY", {
      entry: px,
      stop,
      target: px + (px - stop) * rr,
      confidence: Math.min(0.84, 0.48 + (ind.relVolume - 1) * 0.15 + (ind.rsi - 50) / 120),
      reason: `Price ${((px / ind.vwap - 1) * 100).toFixed(2)}% above VWAP, RSI ${ind.rsi.toFixed(0)}, rel volume ${ind.relVolume.toFixed(2)}.`,
      invalidation: "VWAP breakdown or RSI rolling over through 50.",
      metadata: { vwap: ind.vwap, rsi: ind.rsi, relVolume: ind.relVolume },
    });
  }
  if (!above && ind.rsi <= rsiSell && ind.rsi >= 28 && volOk) {
    const stop = Math.max(px * (1 + slPct), ind.vwap * 1.003);
    return base("vwap_rsi", "v1", "SELL", {
      entry: px,
      stop,
      target: px - (stop - px) * rr,
      confidence: Math.min(0.82, 0.48 + (ind.relVolume - 1) * 0.15 + (50 - ind.rsi) / 120),
      reason: `Price below VWAP, RSI ${ind.rsi.toFixed(0)}, volume confirmation ${ind.relVolume.toFixed(2)}.`,
      invalidation: "Reclaim of VWAP or RSI crossing 50.",
      metadata: { vwap: ind.vwap, rsi: ind.rsi, relVolume: ind.relVolume },
    });
  }
  if (!volOk) {
    return base("vwap_rsi", "v1", "SKIP", {
      confidence: 0.38,
      reason: `Relative volume ${ind.relVolume.toFixed(2)} is thin. VWAP breaks without volume are usually faded.`,
      invalidation: "Rel volume > 1.1 with VWAP side confirmed.",
      metadata: { relVolume: ind.relVolume, rsi: ind.rsi },
    });
  }
  return base("vwap_rsi", "v1", "HOLD", {
    confidence: 0.42,
    reason: `RSI ${ind.rsi.toFixed(0)} not in the continuation band relative to VWAP.`,
    invalidation: "RSI hold above 55 with price over VWAP (or the inverse).",
    metadata: { rsi: ind.rsi, vwap: ind.vwap },
  });
}

function orb(bars: Bar[], cfg: StrategyConfig): StrategyOutput {
  const orBars = cfg.orBars ?? 3;
  const slPct = cfg.slPct ?? 0.008;
  const rr = cfg.rr ?? 1.5;
  if (bars.length < orBars + 5) {
    return base("orb", "v1", "SKIP", {
      confidence: 0.2,
      reason: "Not enough bars to form an opening range.",
      invalidation: "Wait for the opening range to complete.",
    });
  }
  // Use last session's first orBars of the 5m series when available; on daily, use last 3 days as a range proxy.
  const opening = bars.slice(-20, -20 + orBars);
  const window = opening.length ? opening : bars.slice(0, orBars);
  const orh = Math.max(...window.map((b) => b.h));
  const orl = Math.min(...window.map((b) => b.l));
  const px = bars[bars.length - 1]!.c;
  const ind = computeIndicators(bars);
  const rangePct = (orh - orl) / ((orh + orl) / 2);
  if (rangePct > 0.025) {
    return base("orb", "v1", "SKIP", {
      confidence: 0.33,
      reason: `Opening range ${(rangePct * 100).toFixed(2)}% is too wide — breakouts here have poor R.`,
      invalidation: "A compressed opening range (< 1.5%).",
      metadata: { orh, orl, rangePct },
    });
  }
  if (px > orh && ind.relVolume > 1.05) {
    const stop = Math.max(orl, px * (1 - slPct));
    return base("orb", "v1", "BUY", {
      entry: px,
      stop,
      target: px + (px - stop) * rr,
      confidence: Math.min(0.8, 0.5 + ind.relVolume * 0.1),
      reason: `Break of opening-range high ${orh.toFixed(2)} with rel volume ${ind.relVolume.toFixed(2)}.`,
      invalidation: `Back inside the range or stop ${stop.toFixed(2)}.`,
      metadata: { orh, orl, relVolume: ind.relVolume },
    });
  }
  if (px < orl && ind.relVolume > 1.05) {
    const stop = Math.min(orh, px * (1 + slPct));
    return base("orb", "v1", "SELL", {
      entry: px,
      stop,
      target: px - (stop - px) * rr,
      confidence: Math.min(0.78, 0.5 + ind.relVolume * 0.1),
      reason: `Break of opening-range low ${orl.toFixed(2)} with volume.`,
      invalidation: `Back inside the range or stop ${stop.toFixed(2)}.`,
      metadata: { orh, orl, relVolume: ind.relVolume },
    });
  }
  return base("orb", "v1", "HOLD", {
    confidence: 0.4,
    reason: `Price still inside opening range ${orl.toFixed(2)}–${orh.toFixed(2)}.`,
    invalidation: "A volume-confirmed range break.",
    metadata: { orh, orl },
  });
}

export const STRATEGIES: StrategyDef[] = [
  {
    id: "ma_cross",
    name: "MA crossover",
    version: "v1",
    family: "Trend",
    summary: "9/21 SMA cross, ADX filter, ATR-aware stop. Classic, often mediocre after costs.",
    defaults: { fast: 9, slow: 21, slPct: 0.01, rr: 2 },
    params: [
      { key: "fast", label: "Fast SMA", min: 5, max: 15, step: 1 },
      { key: "slow", label: "Slow SMA", min: 18, max: 50, step: 1 },
      { key: "slPct", label: "Stop %", min: 0.005, max: 0.02, step: 0.001 },
      { key: "rr", label: "R:R", min: 1, max: 3, step: 0.5 },
    ],
    run: maCross,
  },
  {
    id: "vwap_rsi",
    name: "VWAP + RSI",
    version: "v1",
    family: "Momentum",
    summary: "Continuation only when price, RSI and relative volume agree with VWAP side.",
    defaults: { rsiBuy: 55, rsiSell: 45, slPct: 0.01, rr: 2 },
    params: [
      { key: "rsiBuy", label: "RSI buy", min: 50, max: 65, step: 1 },
      { key: "rsiSell", label: "RSI sell", min: 35, max: 50, step: 1 },
      { key: "slPct", label: "Stop %", min: 0.005, max: 0.02, step: 0.001 },
      { key: "rr", label: "R:R", min: 1, max: 3, step: 0.5 },
    ],
    run: vwapRsi,
  },
  {
    id: "orb",
    name: "Opening range breakout",
    version: "v1",
    family: "Breakout",
    summary: "Break of a compressed opening range with volume. Skips wide ranges.",
    defaults: { orBars: 3, slPct: 0.008, rr: 1.5 },
    params: [
      { key: "orBars", label: "OR bars", min: 2, max: 6, step: 1 },
      { key: "slPct", label: "Stop %", min: 0.004, max: 0.015, step: 0.001 },
      { key: "rr", label: "R:R", min: 1, max: 3, step: 0.5 },
    ],
    run: orb,
  },
];

export const STRATEGY_BY_ID = Object.fromEntries(STRATEGIES.map((s) => [s.id, s]));

export function runStrategy(id: string, bars: Bar[], cfg?: StrategyConfig): StrategyOutput {
  const def = STRATEGY_BY_ID[id];
  if (!def) throw new Error(id);
  return def.run(bars, { ...def.defaults, ...cfg });
}

export function runAllStrategies(bars: Bar[]): StrategyOutput[] {
  return STRATEGIES.map((s) => s.run(bars, s.defaults));
}

export { classifyRegime };
