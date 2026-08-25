import type { Bar, Indicators } from "./types";

function sma(xs: number[], n: number): number {
  if (xs.length < n) return xs[xs.length - 1] ?? 0;
  let s = 0;
  for (let i = xs.length - n; i < xs.length; i++) s += xs[i]!;
  return s / n;
}

function ema(xs: number[], n: number): number {
  if (!xs.length) return 0;
  const k = 2 / (n + 1);
  let e = xs[0]!;
  for (let i = 1; i < xs.length; i++) e = xs[i]! * k + e * (1 - k);
  return e;
}

function stdev(xs: number[]): number {
  if (xs.length < 2) return 0;
  const m = xs.reduce((a, b) => a + b, 0) / xs.length;
  const v = xs.reduce((a, b) => a + (b - m) ** 2, 0) / (xs.length - 1);
  return Math.sqrt(v);
}

export function rsi(closes: number[], n = 14): number {
  if (closes.length < n + 1) return 50;
  let gain = 0;
  let loss = 0;
  for (let i = closes.length - n; i < closes.length; i++) {
    const d = closes[i]! - closes[i - 1]!;
    if (d >= 0) gain += d;
    else loss -= d;
  }
  const ag = gain / n;
  const al = loss / n;
  if (al === 0) return 100;
  const rs = ag / al;
  return 100 - 100 / (1 + rs);
}

export function atr(bars: Bar[], n = 14): number {
  if (bars.length < 2) return 0;
  const trs: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    const b = bars[i]!;
    const p = bars[i - 1]!;
    trs.push(Math.max(b.h - b.l, Math.abs(b.h - p.c), Math.abs(b.l - p.c)));
  }
  return sma(trs, Math.min(n, trs.length));
}

export function adxPack(bars: Bar[], n = 14): { adx: number; plusDi: number; minusDi: number } {
  if (bars.length < n + 2) return { adx: 15, plusDi: 20, minusDi: 20 };
  const plusDM: number[] = [];
  const minusDM: number[] = [];
  const tr: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    const b = bars[i]!;
    const p = bars[i - 1]!;
    const up = b.h - p.h;
    const down = p.l - b.l;
    plusDM.push(up > down && up > 0 ? up : 0);
    minusDM.push(down > up && down > 0 ? down : 0);
    tr.push(Math.max(b.h - b.l, Math.abs(b.h - p.c), Math.abs(b.l - p.c)));
  }
  const trN = sma(tr, n);
  const pN = sma(plusDM, n);
  const mN = sma(minusDM, n);
  const plusDi = trN ? (100 * pN) / trN : 0;
  const minusDi = trN ? (100 * mN) / trN : 0;
  const dx = plusDi + minusDi === 0 ? 0 : (100 * Math.abs(plusDi - minusDi)) / (plusDi + minusDi);
  return { adx: dx, plusDi, minusDi };
}

export function macdPack(closes: number[]): { macd: number; signal: number } {
  const macd = ema(closes, 12) - ema(closes, 26);
  // approximate signal as ema of last macd path
  const series: number[] = [];
  let e12 = closes[0]!;
  let e26 = closes[0]!;
  const k12 = 2 / 13;
  const k26 = 2 / 27;
  for (let i = 0; i < closes.length; i++) {
    e12 = closes[i]! * k12 + e12 * (1 - k12);
    e26 = closes[i]! * k26 + e26 * (1 - k26);
    series.push(e12 - e26);
  }
  return { macd, signal: ema(series, 9) };
}

export function vwap(bars: Bar[], lookback = 20): number {
  const slice = bars.slice(-lookback);
  let pv = 0;
  let vv = 0;
  for (const b of slice) {
    const tp = (b.h + b.l + b.c) / 3;
    pv += tp * b.v;
    vv += b.v;
  }
  return vv ? pv / vv : slice[slice.length - 1]?.c ?? 0;
}

export function realizedVol(closes: number[], n = 20): number {
  if (closes.length < n + 1) return 0.15;
  const rets: number[] = [];
  for (let i = closes.length - n; i < closes.length; i++) {
    rets.push(Math.log(closes[i]! / closes[i - 1]!));
  }
  return stdev(rets) * Math.sqrt(252);
}

export function computeIndicators(bars: Bar[]): Indicators {
  const closes = bars.map((b) => b.c);
  const vols = bars.map((b) => b.v);
  const { adx, plusDi, minusDi } = adxPack(bars);
  const { macd, signal } = macdPack(closes);
  const mid = sma(closes, 20);
  const sd = stdev(closes.slice(-20));
  const avgVol = sma(vols, 20);
  const lastVol = vols[vols.length - 1] ?? 0;
  const volSlice = vols.slice(-20);
  const vz = sd && volSlice.length ? (lastVol - avgVol) / (stdev(volSlice) || 1) : 0;
  return {
    smaFast: sma(closes, 9),
    smaSlow: sma(closes, 21),
    ema9: ema(closes, 9),
    ema21: ema(closes, 21),
    rsi: rsi(closes, 14),
    macd,
    macdSignal: signal,
    atr: atr(bars, 14),
    adx,
    plusDi,
    minusDi,
    vwap: vwap(bars, 20),
    bbUpper: mid + 2 * sd,
    bbLower: mid - 2 * sd,
    bbMid: mid,
    realizedVol: realizedVol(closes, 20),
    volumeZ: vz,
    relVolume: avgVol ? lastVol / avgVol : 1,
  };
}

export function indicatorAt(bars: Bar[], idx: number): Indicators {
  return computeIndicators(bars.slice(0, idx + 1));
}

export function returns(closes: number[], n: number): number {
  if (closes.length < n + 1) return 0;
  const a = closes[closes.length - 1 - n]!;
  return a ? (closes[closes.length - 1]! - a) / a : 0;
}
