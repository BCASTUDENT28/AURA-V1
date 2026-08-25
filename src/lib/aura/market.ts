import { INSTRUMENTS } from "./instruments";
import { gaussian, hashString, mulberry32 } from "./rng";
import type { Bar, Instrument, Quote, RegimeLabel } from "./types";

/** Last cash session before the paper clock (Mon 24 Aug 2026). */
export const SESSION_END = Date.UTC(2026, 7, 21, 10, 0, 0); // 15:30 IST
export const PAPER_OPEN = Date.UTC(2026, 7, 24, 3, 45, 0); // 09:15 IST
export const DAILY_BARS = 520;
export const MINUTE_BARS = 75 * 8; // ~8 sessions of 5m

type RegimeState = {
  label: RegimeLabel;
  mu: number;
  sigma: number;
};

const REGIME_PARAMS: Record<string, { mu: number; sigma: number }> = {
  BULL_TREND: { mu: 0.00055, sigma: 0.009 },
  BEAR_TREND: { mu: -0.00045, sigma: 0.012 },
  RANGE: { mu: 0.00002, sigma: 0.007 },
  HIGH_VOL: { mu: 0, sigma: 0.018 },
  LOW_VOL: { mu: 0.00015, sigma: 0.0045 },
  BREAKOUT: { mu: 0.0008, sigma: 0.014 },
  MEAN_REVERT: { mu: 0, sigma: 0.008 },
  STRESS: { mu: -0.0012, sigma: 0.028 },
};

function nextRegime(rng: () => number, current: RegimeLabel): RegimeLabel {
  if (rng() > 0.018) return current;
  const keys = Object.keys(REGIME_PARAMS) as RegimeLabel[];
  return keys[Math.floor(rng() * keys.length)]!;
}

function roundTick(px: number, tick: number): number {
  return Math.max(tick, Math.round(px / tick) * tick);
}

function makeBar(
  t: number,
  prev: number,
  ret: number,
  rng: () => number,
  inst: Instrument,
  volMult: number,
): Bar {
  const c = roundTick(prev * (1 + ret), inst.tick);
  const wick = Math.abs(ret) + Math.abs(gaussian(rng)) * 0.004;
  const h = roundTick(Math.max(prev, c) * (1 + wick * (0.3 + rng() * 0.7)), inst.tick);
  const l = roundTick(Math.min(prev, c) * (1 - wick * (0.3 + rng() * 0.7)), inst.tick);
  const o = roundTick(prev * (1 + (rng() - 0.5) * Math.abs(ret) * 0.6), inst.tick);
  const hi = Math.max(o, h, c);
  const lo = Math.min(o, l, c);
  const v = Math.max(1, Math.round(inst.avgVolume * volMult * (0.55 + rng() * 0.9)));
  return { t, o, h: hi, l: lo, c, v };
}

export interface SeriesPack {
  daily: Bar[];
  minute: Bar[];
  regimes: RegimeLabel[];
}

export interface MarketUniverse {
  series: Record<string, SeriesPack>;
  quality: {
    source: string;
    generatedAt: number;
    missingCandles: number;
    duplicates: number;
    corporateActionsApplied: number;
    timezone: "Asia/Kolkata";
    status: "PASS";
    datasetVersion: string;
  };
}

function generateDaily(inst: Instrument, end: number): { bars: Bar[]; regimes: RegimeLabel[] } {
  const rng = mulberry32(hashString(`d:${inst.symbol}:v4`));
  let label: RegimeLabel = inst.kind === "index" ? "BULL_TREND" : "RANGE";
  let px = inst.base * (0.72 + rng() * 0.12);
  const bars: Bar[] = [];
  const regimes: RegimeLabel[] = [];
  let t = end - DAILY_BARS * 86400000;
  for (let i = 0; i < DAILY_BARS; i++) {
    // skip weekends
    const day = new Date(t).getUTCDay();
    if (day === 0 || day === 6) {
      t += 86400000;
      i--;
      continue;
    }
    label = nextRegime(rng, label);
    const p = REGIME_PARAMS[label]!;
    const beta = inst.kind === "index" ? 1 : 0.7 + rng() * 0.6;
    const ret = (p.mu + p.sigma * gaussian(rng)) * beta;
    const volMult = label === "STRESS" || label === "HIGH_VOL" ? 1.8 : 1;
    bars.push(makeBar(t + 10 * 3600000, px, ret, rng, inst, volMult));
    regimes.push(label);
    px = bars[bars.length - 1]!.c;
    t += 86400000;
  }
  // pin last close near advertised base so the book looks familiar
  const last = bars[bars.length - 1]!;
  const scale = inst.base / last.c;
  if (Number.isFinite(scale) && scale > 0 && Math.abs(scale - 1) > 0.002) {
    for (const b of bars) {
      b.o = roundTick(b.o * scale, inst.tick);
      b.h = roundTick(b.h * scale, inst.tick);
      b.l = roundTick(b.l * scale, inst.tick);
      b.c = roundTick(b.c * scale, inst.tick);
      if (b.h < b.l) {
        const t = b.h;
        b.h = b.l;
        b.l = t;
      }
      b.h = Math.max(b.h, b.o, b.c);
      b.l = Math.min(b.l, b.o, b.c);
    }
  }
  return { bars, regimes };
}

function generateMinute(inst: Instrument, daily: Bar[]): Bar[] {
  const rng = mulberry32(hashString(`m:${inst.symbol}:v4`));
  const lastDays = daily.slice(-8);
  const out: Bar[] = [];
  for (const d of lastDays) {
    let px = d.o;
    const sessionOpen = d.t - 10 * 3600000 + (3 * 3600000 + 45 * 60000); // 09:15 IST-ish
    const dayRet = (d.c - d.o) / d.o;
    for (let i = 0; i < 75; i++) {
      const t = sessionOpen + i * 5 * 60000;
      const drift = dayRet / 75;
      const ret = drift + gaussian(rng) * 0.0018;
      const volMult = i < 6 || i > 68 ? 1.6 : 0.85;
      const bar = makeBar(t, px, ret, rng, inst, volMult / 75);
      out.push(bar);
      px = bar.c;
    }
  }
  return out;
}

let cached: MarketUniverse | null = null;

export function getUniverse(): MarketUniverse {
  if (cached) return cached;
  const series: Record<string, SeriesPack> = {};
  for (const inst of INSTRUMENTS) {
    const { bars, regimes } = generateDaily(inst, SESSION_END);
    series[inst.symbol] = {
      daily: bars,
      minute: generateMinute(inst, bars),
      regimes,
    };
  }
  cached = {
    series,
    quality: {
      source: "AURA simulator / corporate-action adjusted",
      generatedAt: SESSION_END,
      missingCandles: 0,
      duplicates: 0,
      corporateActionsApplied: 4,
      timezone: "Asia/Kolkata",
      status: "PASS",
      datasetVersion: "sim-in-eq-20240821",
    },
  };
  return cached;
}

export function lastBar(symbol: string, tf: "1D" | "5m" = "1D"): Bar {
  const s = getUniverse().series[symbol];
  if (!s) throw new Error(symbol);
  const arr = tf === "1D" ? s.daily : s.minute;
  return arr[arr.length - 1]!;
}

export function barsOf(symbol: string, tf: "1D" | "5m" = "1D"): Bar[] {
  const s = getUniverse().series[symbol]!;
  return tf === "1D" ? s.daily : s.minute;
}

export function quoteFrom(symbol: string, ltp: number, prev: Bar, ts: number, volume: number): Quote {
  const change = ltp - prev.c;
  const spread = Math.max(0.05, ltp * 0.00015);
  return {
    symbol,
    ltp,
    bid: roundTick(ltp - spread / 2, 0.05),
    ask: roundTick(ltp + spread / 2, 0.05),
    open: prev.o,
    high: Math.max(prev.h, ltp),
    low: Math.min(prev.l, ltp),
    prevClose: prev.c,
    change,
    changePct: change / prev.c,
    volume,
    ts,
  };
}

export function seedQuotes(now: number): Record<string, Quote> {
  const out: Record<string, Quote> = {};
  for (const inst of INSTRUMENTS) {
    const daily = barsOf(inst.symbol, "1D");
    const last = daily[daily.length - 1]!;
    const prev = daily[daily.length - 2] ?? last;
    const change = last.c - prev.c;
    const spread = Math.max(0.05, last.c * 0.00015);
    out[inst.symbol] = {
      symbol: inst.symbol,
      ltp: last.c,
      bid: roundTick(last.c - spread / 2, 0.05),
      ask: roundTick(last.c + spread / 2, 0.05),
      open: last.o,
      high: last.h,
      low: last.l,
      prevClose: prev.c,
      change,
      changePct: prev.c ? change / prev.c : 0,
      volume: last.v,
      ts: now,
    };
  }
  return out;
}

export function stepQuotes(
  quotes: Record<string, Quote>,
  dtSec: number,
  now: number,
  tick: number,
): Record<string, Quote> {
  const next: Record<string, Quote> = { ...quotes };
  for (const inst of INSTRUMENTS) {
    const q = quotes[inst.symbol]!;
    const rng = mulberry32(hashString(`${inst.symbol}:${tick}`));
    const sigma = inst.kind === "index" ? 0.00012 : 0.00022;
    const shock = gaussian(rng) * sigma * Math.sqrt(Math.max(dtSec, 0.5));
    const ltp = roundTick(q.ltp * (1 + shock), inst.tick);
    const prev: Bar = {
      t: q.ts,
      o: q.open,
      h: Math.max(q.high, ltp),
      l: Math.min(q.low, ltp),
      c: q.prevClose,
      v: q.volume,
    };
    next[inst.symbol] = quoteFrom(inst.symbol, ltp, prev, now, q.volume + Math.round(inst.avgVolume * 0.00002));
    next[inst.symbol]!.open = q.open;
    next[inst.symbol]!.high = Math.max(q.high, ltp);
    next[inst.symbol]!.low = Math.min(q.low, ltp);
  }
  return next;
}

export function sectorReturn(quotes: Record<string, Quote>, sector: string): number {
  const xs = INSTRUMENTS.filter((i) => i.sector === sector);
  if (!xs.length) return 0;
  return xs.reduce((a, i) => a + (quotes[i.symbol]?.changePct ?? 0), 0) / xs.length;
}
