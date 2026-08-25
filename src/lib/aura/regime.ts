import { computeIndicators } from "./indicators";
import type { Bar, Regime, RegimeLabel } from "./types";

export function classifyRegime(bars: Bar[]): Regime {
  const ind = computeIndicators(bars);
  const vol = ind.realizedVol;
  const adx = ind.adx;
  let label: RegimeLabel = "RANGE";
  let notes = "ADX below trend threshold; treat as range until proven otherwise.";

  if (vol > 0.32) {
    label = "STRESS";
    notes = "Realized vol in the tail. Size down or skip. Stops will be noisy.";
  } else if (vol > 0.24) {
    label = "HIGH_VOL";
    notes = "Elevated realized vol. Widen risk bands; fade breakouts that lack volume.";
  } else if (vol < 0.1 && adx < 18) {
    label = "LOW_VOL";
    notes = "Compressed vol. Breakout strategies may wake up; mean-reversion still valid.";
  } else if (adx >= 25 && ind.plusDi > ind.minusDi) {
    label = "BULL_TREND";
    notes = "ADX confirms directional trend with +DI lead. Momentum/trend-follow preferred.";
  } else if (adx >= 25 && ind.minusDi > ind.plusDi) {
    label = "BEAR_TREND";
    notes = "ADX confirms directional trend with −DI lead. Don't fade without evidence.";
  } else if (adx >= 20 && ind.relVolume > 1.4 && Math.abs(ind.rsi - 50) > 12) {
    label = "BREAKOUT";
    notes = "Volume expansion with directional RSI. Breakout family has the ball.";
  } else if (adx < 20 && ind.rsi > 30 && ind.rsi < 70) {
    label = "MEAN_REVERT";
    notes = "No trend, RSI mid-band. Mean-reversion historically less punished here.";
  } else {
    label = "RANGE";
  }

  const trendStrength = Math.min(1, adx / 40);
  const volPercentile = Math.max(0, Math.min(1, (vol - 0.08) / 0.28));
  return {
    label,
    adx,
    realizedVol: vol,
    volPercentile,
    trendStrength,
    notes,
  };
}

export function regimeFits(strategyId: string, regime: RegimeLabel): number {
  const table: Record<string, RegimeLabel[]> = {
    ma_cross: ["BULL_TREND", "BEAR_TREND", "BREAKOUT"],
    vwap_rsi: ["BULL_TREND", "BREAKOUT", "LOW_VOL"],
    orb: ["BREAKOUT", "BULL_TREND", "BEAR_TREND", "HIGH_VOL"],
  };
  const ok = table[strategyId] ?? [];
  if (ok.includes(regime)) return 1;
  if (regime === "STRESS") return 0.15;
  if (regime === "RANGE" || regime === "MEAN_REVERT") return 0.45;
  return 0.6;
}
