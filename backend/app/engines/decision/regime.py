"""
backend/app/engines/decision/regime.py

Port of src/lib/aura/regime.ts
Regime classification thresholds are kept bit-for-bit identical.
"""

from __future__ import annotations

from backend.app.engines.decision.indicators import compute_indicators
from backend.app.schemas.types import Bar, Regime, RegimeLabel


def classify_regime(bars: list[Bar]) -> Regime:
    ind = compute_indicators(bars)
    return _classify_from_scalars(ind.realizedVol, ind.adx, ind.plusDi, ind.minusDi, ind.relVolume, ind.rsi)


def _classify_from_scalars(vol: float, adx: float, plus_di: float, minus_di: float, rel_vol: float, rsi: float) -> Regime:
    label: RegimeLabel = "RANGE"
    notes = "ADX below trend threshold; treat as range until proven otherwise."

    if vol > 0.32:
        label = "STRESS"
        notes = "Realized vol in the tail. Size down or skip. Stops will be noisy."
    elif vol > 0.24:
        label = "HIGH_VOL"
        notes = "Elevated realized vol. Widen risk bands; fade breakouts that lack volume."
    elif vol < 0.1 and adx < 18:
        label = "LOW_VOL"
        notes = "Compressed vol. Breakout strategies may wake up; mean-reversion still valid."
    elif adx >= 25 and plus_di > minus_di:
        label = "BULL_TREND"
        notes = "ADX confirms directional trend with +DI lead. Momentum/trend-follow preferred."
    elif adx >= 25 and minus_di > plus_di:
        label = "BEAR_TREND"
        notes = "ADX confirms directional trend with \u2212DI lead. Don't fade without evidence."
    elif adx >= 20 and rel_vol > 1.4 and abs(rsi - 50) > 12:
        label = "BREAKOUT"
        notes = "Volume expansion with directional RSI. Breakout family has the ball."
    elif adx < 20 and rsi > 30 and rsi < 70:
        label = "MEAN_REVERT"
        notes = "No trend, RSI mid-band. Mean-reversion historically less punished here."
    else:
        label = "RANGE"

    trend_strength = min(1.0, adx / 40)
    vol_percentile = max(0.0, min(1.0, (vol - 0.08) / 0.28))

    return Regime(
        label=label,
        adx=adx,
        realizedVol=vol,
        volPercentile=vol_percentile,
        trendStrength=trend_strength,
        notes=notes,
    )


def regime_fits(strategy_id: str, regime: RegimeLabel) -> float:
    table: dict[str, list[str]] = {
        "ma_cross":  ["BULL_TREND", "BEAR_TREND", "BREAKOUT"],
        "vwap_rsi":  ["BULL_TREND", "BREAKOUT", "LOW_VOL"],
        "orb":       ["BREAKOUT", "BULL_TREND", "BEAR_TREND", "HIGH_VOL"],
    }
    ok = table.get(strategy_id, [])
    if regime in ok:
        return 1.0
    if regime == "STRESS":
        return 0.15
    if regime in ("RANGE", "MEAN_REVERT"):
        return 0.45
    return 0.6
