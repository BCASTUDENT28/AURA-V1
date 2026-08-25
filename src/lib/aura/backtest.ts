import { estimateCosts } from "./cost";
import { getInstrument } from "./instruments";
import { barsOf } from "./market";
import { classifyRegime } from "./regime";
import { STRATEGY_BY_ID } from "./strategies";
import type {
  BacktestMetrics,
  BacktestResult,
  BacktestTrade,
  Bar,
  ProductType,
  RegimeLabel,
  StrategyConfig,
  Timeframe,
} from "./types";
import { STARTING_CASH } from "./types";

function metricsOf(trades: BacktestTrade[], equity: { t: number; v: number }[], from: number, to: number): BacktestMetrics {
  const wins = trades.filter((t) => t.pnl > 0);
  const losses = trades.filter((t) => t.pnl <= 0);
  const netPnl = trades.reduce((a, t) => a + t.pnl, 0);
  const start = equity[0]?.v ?? STARTING_CASH;
  const end = equity[equity.length - 1]?.v ?? start;
  const totalReturn = start ? (end - start) / start : 0;
  const years = Math.max(1 / 252, (to - from) / (365.25 * 86400000));
  const cagr = years > 0 ? Math.pow(Math.max(1e-9, 1 + totalReturn), 1 / years) - 1 : 0;
  const grossWin = wins.reduce((a, t) => a + t.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((a, t) => a + t.pnl, 0));
  const profitFactor = grossLoss === 0 ? (grossWin > 0 ? 99 : 0) : grossWin / grossLoss;
  const rets = equity.slice(1).map((e, i) => {
    const p = equity[i]!.v;
    return p ? (e.v - p) / p : 0;
  });
  const mean = rets.length ? rets.reduce((a, b) => a + b, 0) / rets.length : 0;
  const sd = rets.length
    ? Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, rets.length - 1))
    : 0;
  const sharpe = sd ? (mean / sd) * Math.sqrt(252) : 0;
  const neg = rets.filter((r) => r < 0);
  const dsd = neg.length
    ? Math.sqrt(neg.reduce((a, b) => a + b * b, 0) / neg.length)
    : 0;
  const sortino = dsd ? (mean / dsd) * Math.sqrt(252) : 0;
  let peak = start;
  let maxDd = 0;
  for (const e of equity) {
    peak = Math.max(peak, e.v);
    maxDd = Math.max(maxDd, peak ? (peak - e.v) / peak : 0);
  }
  const byMonth = new Map<string, number>();
  for (let i = 1; i < equity.length; i++) {
    const d = new Date(equity[i]!.t);
    const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
    const r = equity[i - 1]!.v ? (equity[i]!.v - equity[i - 1]!.v) / equity[i - 1]!.v : 0;
    byMonth.set(key, (byMonth.get(key) ?? 0) + r);
  }
  const regimes: RegimeLabel[] = [
    "BULL_TREND",
    "BEAR_TREND",
    "RANGE",
    "HIGH_VOL",
    "LOW_VOL",
    "BREAKOUT",
    "MEAN_REVERT",
    "STRESS",
  ];
  const byRegime = regimes
    .map((regime) => {
      const ts = trades.filter((t) => t.regime === regime);
      if (!ts.length) return null;
      return {
        regime,
        trades: ts.length,
        winRate: ts.filter((t) => t.pnl > 0).length / ts.length,
        pnl: ts.reduce((a, t) => a + t.pnl, 0),
      };
    })
    .filter((x): x is NonNullable<typeof x> => x !== null);

  return {
    trades: trades.length,
    wins: wins.length,
    losses: losses.length,
    winRate: trades.length ? wins.length / trades.length : 0,
    lossRate: trades.length ? losses.length / trades.length : 0,
    totalReturn,
    cagr,
    netPnl,
    profitFactor,
    expectancy: trades.length ? netPnl / trades.length : 0,
    avgR: trades.length ? trades.reduce((a, t) => a + t.rMultiple, 0) / trades.length : 0,
    sharpe,
    sortino,
    maxDrawdown: maxDd,
    recoveryFactor: maxDd ? totalReturn / maxDd : 0,
    avgHoldBars: trades.length ? trades.reduce((a, t) => a + (t.exitTs - t.entryTs) / 86400000, 0) / trades.length : 0,
    bestTrade: trades.length ? Math.max(...trades.map((t) => t.pnl)) : 0,
    worstTrade: trades.length ? Math.min(...trades.map((t) => t.pnl)) : 0,
    costsTotal: trades.reduce((a, t) => a + t.costs, 0),
    monthly: [...byMonth.entries()].map(([month, ret]) => ({ month, ret })),
    byRegime,
    equity,
  };
}

function runWindow(
  bars: Bar[],
  strategyId: string,
  cfg: StrategyConfig,
  product: ProductType,
  symbol: string,
): { trades: BacktestTrade[]; equity: { t: number; v: number }[] } {
  const def = STRATEGY_BY_ID[strategyId]!;
  const inst = getInstrument(symbol);
  let cash = STARTING_CASH;
  let qty = 0;
  let side: "BUY" | "SELL" | null = null;
  let entry = 0;
  let stop = 0;
  let target = 0;
  let entryTs = 0;
  let entryRegime: RegimeLabel = "RANGE";
  const trades: BacktestTrade[] = [];
  const equity: { t: number; v: number }[] = [];
  const riskFrac = 0.08;

  const closePos = (bar: Bar, px: number, reason: string) => {
    if (!qty || !side) return;
    const dir = side === "BUY" ? 1 : -1;
    const turnover = px * qty;
    const costs =
      estimateCosts({ turnover: entry * qty, side, product, kind: inst.kind }).total +
      estimateCosts({
        turnover,
        side: side === "BUY" ? "SELL" : "BUY",
        product,
        kind: inst.kind,
      }).total;
    const pnl = dir * (px - entry) * qty - costs;
    const risk = Math.abs(entry - stop) * qty || entry * 0.01 * qty;
    cash += dir === 1 ? qty * px : qty * (2 * entry - px);
    cash -= costs;
    trades.push({
      symbol,
      side,
      entryTs,
      exitTs: bar.t,
      entry,
      exit: px,
      qty,
      pnl,
      pnlPct: entry ? pnl / (entry * qty) : 0,
      rMultiple: risk ? pnl / risk : 0,
      costs,
      reason,
      regime: entryRegime,
    });
    qty = 0;
    side = null;
  };

  for (let i = 40; i < bars.length; i++) {
    const window = bars.slice(0, i + 1);
    const bar = bars[i]!;
    const sig = def.run(window, { ...def.defaults, ...cfg });
    const regime = classifyRegime(window);

    if (qty && side) {
      if (side === "BUY" && (bar.l <= stop || bar.h >= target)) {
        const px = bar.l <= stop ? stop : target;
        closePos(bar, px, bar.l <= stop ? "stop" : "target");
      } else if (side === "SELL" && (bar.h >= stop || bar.l <= target)) {
        const px = bar.h >= stop ? stop : target;
        closePos(bar, px, bar.h >= stop ? "stop" : "target");
      } else if (sig.action === "SKIP" || (side === "BUY" && sig.action === "SELL") || (side === "SELL" && sig.action === "BUY")) {
        closePos(bar, bar.c, "signal flip");
      }
    }

    if (!qty && (sig.action === "BUY" || sig.action === "SELL") && sig.entry && sig.stop) {
      const px = bar.c;
      const riskPer = Math.abs(px - sig.stop) || px * 0.01;
      const size = Math.max(1, Math.floor((cash * riskFrac) / (riskPer || px)));
      const notional = size * px;
      if (notional > 0 && notional < cash * 0.95) {
        const costs = estimateCosts({
          turnover: notional,
          side: sig.action,
          product,
          kind: inst.kind,
        }).total;
        cash -= costs;
        if (sig.action === "BUY") cash -= notional;
        else cash -= 0; // short proceeds stay as margin in this simple book
        qty = size;
        side = sig.action;
        entry = px;
        stop = sig.stop;
        target = sig.target ?? (sig.action === "BUY" ? px + (px - stop) * 2 : px - (stop - px) * 2);
        entryTs = bar.t;
        entryRegime = regime.label;
      }
    }

    const mtm = qty && side ? (side === "BUY" ? qty * bar.c : qty * (2 * entry - bar.c)) : 0;
    equity.push({ t: bar.t, v: cash + mtm });
  }
  const last = bars[bars.length - 1]!;
  if (qty) closePos(last, last.c, "eod flatten");
  return { trades, equity };
}

export function runBacktest(opts: {
  strategyId: string;
  symbol: string;
  timeframe?: Timeframe;
  config?: StrategyConfig;
  product?: ProductType;
}): BacktestResult {
  const timeframe = opts.timeframe ?? "1D";
  const product = opts.product ?? "INTRADAY";
  const cfg = opts.config ?? {};
  const def = STRATEGY_BY_ID[opts.strategyId];
  if (!def) throw new Error(opts.strategyId);
  const bars = barsOf(opts.symbol, timeframe);
  const { trades, equity } = runWindow(bars, opts.strategyId, cfg, product, opts.symbol);
  const from = bars[0]!.t;
  const to = bars[bars.length - 1]!.t;
  const m = metricsOf(trades, equity, from, to);

  const n = bars.length;
  const slices = [
    { train: [0, Math.floor(n * 0.5)], test: [Math.floor(n * 0.5), Math.floor(n * 0.7)] },
    { train: [0, Math.floor(n * 0.7)], test: [Math.floor(n * 0.7), Math.floor(n * 0.85)] },
    { train: [0, Math.floor(n * 0.85)], test: [Math.floor(n * 0.85), n] },
  ];
  const walkForward = slices.map((s, i) => {
    const testBars = bars.slice(s.test[0], s.test[1]);
    const r = runWindow(testBars, opts.strategyId, cfg, product, opts.symbol);
    const tm = metricsOf(r.trades, r.equity, testBars[0]?.t ?? from, testBars[testBars.length - 1]?.t ?? to);
    const fmt = (idx: number) => new Date(bars[Math.min(idx, bars.length - 1)]!.t).toISOString().slice(0, 10);
    return {
      window: `WF-${i + 1}`,
      train: `${fmt(s.train[0]!)} → ${fmt(s.train[1]! - 1)}`,
      test: `${fmt(s.test[0]!)} → ${fmt(s.test[1]! - 1)}`,
      testReturn: tm.totalReturn,
      testWinRate: tm.winRate,
      testSharpe: tm.sharpe,
    };
  });

  const neighborKeys = Object.keys({ ...def.defaults, ...cfg });
  const neighborRets: number[] = [];
  for (const key of neighborKeys.slice(0, 3)) {
    const base = { ...def.defaults, ...cfg };
    const step = def.params.find((p) => p.key === key)?.step ?? 1;
    for (const dir of [-1, 1]) {
      const c = { ...base, [key]: (base[key] ?? 0) + dir * step };
      const r = runWindow(bars, opts.strategyId, c, product, opts.symbol);
      const tm = metricsOf(r.trades, r.equity, from, to);
      neighborRets.push(tm.totalReturn);
    }
  }
  const mean = neighborRets.reduce((a, b) => a + b, 0) / Math.max(1, neighborRets.length);
  const neighborStd = Math.sqrt(
    neighborRets.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, neighborRets.length),
  );
  const warning =
    neighborStd > 0.15
      ? "Neighbor parameters swing hard — treat this as a fragile fit, not an edge."
      : m.maxDrawdown > 0.25
        ? "Drawdown is large relative to return. Do not scale."
        : null;

  return {
    strategyId: opts.strategyId,
    version: def.version,
    symbol: opts.symbol,
    timeframe,
    from,
    to,
    config: { ...def.defaults, ...cfg },
    product,
    metrics: m,
    trades,
    walkForward,
    robust: { neighborStd, warning },
  };
}

export function experimentGrid(opts: {
  strategyId: string;
  symbol: string;
  product?: ProductType;
}): { label: string; config: StrategyConfig; totalReturn: number; sharpe: number; maxDrawdown: number; trades: number; winRate: number }[] {
  const def = STRATEGY_BY_ID[opts.strategyId];
  if (!def) return [];
  const rsiVals = [50, 55, 60];
  const slVals = [0.005, 0.01, 0.015];
  const rrVals = [1, 2, 3];
  const rows = [];
  const combos: StrategyConfig[] = [];
  if (opts.strategyId === "vwap_rsi") {
    for (const rsiBuy of rsiVals) for (const slPct of slVals) for (const rr of rrVals) combos.push({ rsiBuy, slPct, rr });
  } else if (opts.strategyId === "ma_cross") {
    for (const fast of [7, 9, 12]) for (const slPct of slVals) for (const rr of rrVals) combos.push({ fast, slPct, rr });
  } else {
    for (const orBars of [2, 3, 4]) for (const slPct of slVals) for (const rr of rrVals) combos.push({ orBars, slPct, rr });
  }
  for (const config of combos) {
    const r = runBacktest({ ...opts, config });
    rows.push({
      label: Object.entries(config)
        .map(([k, v]) => `${k}=${v}`)
        .join(" · "),
      config,
      totalReturn: r.metrics.totalReturn,
      sharpe: r.metrics.sharpe,
      maxDrawdown: r.metrics.maxDrawdown,
      trades: r.metrics.trades,
      winRate: r.metrics.winRate,
    });
  }
  rows.sort((a, b) => b.sharpe - a.sharpe);
  return rows;
}
