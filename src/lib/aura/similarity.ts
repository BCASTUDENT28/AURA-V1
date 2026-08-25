import { computeIndicators } from "./indicators";
import type { Bar, SimilarMatch } from "./types";

const memo = new Map<string, SimilarMatch>();

function feat(bars: Bar[], i: number): number[] {
  const w = bars.slice(Math.max(0, i - 30), i + 1);
  const ind = computeIndicators(w);
  const c = bars[i]!.c;
  const p5 = bars[i - 5]?.c ?? c;
  const p20 = bars[i - 20]?.c ?? c;
  return [
    (c - p5) / p5,
    (c - p20) / p20,
    (ind.rsi - 50) / 50,
    ind.adx / 40,
    ind.realizedVol,
    Math.tanh(ind.volumeZ / 2),
    (c - ind.vwap) / (ind.atr || c * 0.01),
  ];
}

function dist(a: number[], b: number[]): number {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += (a[i]! - b[i]!) ** 2;
  return Math.sqrt(s);
}

export function similarSetups(bars: Bar[], horizon = 5, cacheKey?: string): SimilarMatch {
  if (cacheKey && memo.has(cacheKey)) return memo.get(cacheKey)!;
  if (bars.length < 80) {
    return { n: 0, winRate: 0, avgReturn: 0, avgMae: 0, avgMfe: 0, avgHoldBars: horizon };
  }
  const last = bars.length - 1;
  const target = feat(bars, last);
  const hits: { i: number; d: number }[] = [];
  for (let i = 40; i < last - horizon - 1; i += 3) {
    const d = dist(feat(bars, i), target);
    if (d < 0.9) hits.push({ i, d });
  }
  hits.sort((a, b) => a.d - b.d);
  const top = hits.slice(0, 32);
  if (!top.length) {
    const empty = { n: 0, winRate: 0, avgReturn: 0, avgMae: 0, avgMfe: 0, avgHoldBars: horizon };
    if (cacheKey) memo.set(cacheKey, empty);
    return empty;
  }
  let wins = 0;
  let ret = 0;
  let mae = 0;
  let mfe = 0;
  for (const h of top) {
    const entry = bars[h.i]!.c;
    const future = bars.slice(h.i, h.i + horizon + 1);
    const exit = future[future.length - 1]!.c;
    const r = (exit - entry) / entry;
    ret += r;
    if (r > 0) wins++;
    let min = 0;
    let max = 0;
    for (const b of future) {
      min = Math.min(min, (b.l - entry) / entry);
      max = Math.max(max, (b.h - entry) / entry);
    }
    mae += min;
    mfe += max;
  }
  const n = top.length;
  const match = {
    n,
    winRate: wins / n,
    avgReturn: ret / n,
    avgMae: mae / n,
    avgMfe: mfe / n,
    avgHoldBars: horizon,
  };
  if (cacheKey) memo.set(cacheKey, match);
  return match;
}
