"""
backend/app/engines/decision/strategies.py

Port of src/lib/aura/strategies.ts
MA crossover, VWAP+RSI, and ORB strategies — logic kept identical to TS
for parity testing. Parameter defaults match TypeScript defaults exactly.
"""

from __future__ import annotations

from backend.app.engines.decision.indicators import compute_indicators
from backend.app.engines.decision.regime import classify_regime
from backend.app.schemas.types import Bar, StrategyOutput


def _base(
    id_: str,
    version: str,
    action: str,
    entry=None,
    stop=None,
    target=None,
    confidence: float = 0.5,
    reason: str = "",
    invalidation: str = "",
    metadata: dict = None,
) -> StrategyOutput:
    return StrategyOutput(
        strategyId=id_,
        version=version,
        action=action,
        entry=entry,
        stop=stop,
        target=target,
        confidence=confidence,
        reason=reason,
        invalidation=invalidation,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# MA Crossover
# ---------------------------------------------------------------------------

def ma_cross(bars: list[Bar], cfg: dict = None) -> StrategyOutput:
    cfg = cfg or {}
    fast_n = cfg.get("fast", 9)
    slow_n = cfg.get("slow", 21)
    sl_pct = cfg.get("slPct", 0.01)
    rr = cfg.get("rr", 2)

    ind = compute_indicators(bars)
    px = bars[-1].c
    prev = compute_indicators(bars[:-1])

    crossed_up = prev.smaFast <= prev.smaSlow and ind.smaFast > ind.smaSlow
    crossed_dn = prev.smaFast >= prev.smaSlow and ind.smaFast < ind.smaSlow
    aligned_up = ind.smaFast > ind.smaSlow and ind.ema9 > ind.ema21
    aligned_dn = ind.smaFast < ind.smaSlow and ind.ema9 < ind.ema21

    if ind.adx < 15:
        return _base(
            "ma_cross", "v1", "SKIP",
            confidence=0.35,
            reason=f"ADX {ind.adx:.1f} is below 15 — crossover in a dead trend is noise.",
            invalidation="Wait for ADX > 18 before acting on a cross.",
            metadata={"adx": ind.adx, "fast": ind.smaFast, "slow": ind.smaSlow},
        )

    if crossed_up or (aligned_up and ind.rsi > 52 and ind.rsi < 72):
        stop = px * (1 - sl_pct)
        return _base(
            "ma_cross", "v1", "BUY",
            entry=px, stop=stop, target=px + (px - stop) * rr,
            confidence=min(0.82, 0.5 + ind.adx / 80 + (0.1 if crossed_up else 0)),
            reason=(
                f"SMA {fast_n} crossed above SMA {slow_n} with ADX {ind.adx:.1f}."
                if crossed_up
                else f"Fast SMA remains above slow; RSI {ind.rsi:.0f} supports continuation."
            ),
            invalidation=f"Close back below SMA {slow_n} or stop at {stop:.2f}.",
            metadata={"fast": fast_n, "slow": slow_n, "adx": ind.adx, "rsi": ind.rsi},
        )

    if crossed_dn or (aligned_dn and ind.rsi < 48 and ind.rsi > 28):
        stop = px * (1 + sl_pct)
        return _base(
            "ma_cross", "v1", "SELL",
            entry=px, stop=stop, target=px - (stop - px) * rr,
            confidence=min(0.8, 0.5 + ind.adx / 80 + (0.1 if crossed_dn else 0)),
            reason=(
                f"SMA {fast_n} crossed below SMA {slow_n} with ADX {ind.adx:.1f}."
                if crossed_dn
                else f"Fast SMA remains below slow; RSI {ind.rsi:.0f} supports downside."
            ),
            invalidation=f"Close back above SMA {slow_n} or stop at {stop:.2f}.",
            metadata={"fast": fast_n, "slow": slow_n, "adx": ind.adx, "rsi": ind.rsi},
        )

    return _base(
        "ma_cross", "v1", "HOLD",
        confidence=0.45,
        reason="No fresh cross and RSI is mid-range. Stand aside.",
        invalidation="A 9/21 cross with ADX > 18.",
        metadata={"rsi": ind.rsi, "adx": ind.adx},
    )


# ---------------------------------------------------------------------------
# VWAP + RSI
# ---------------------------------------------------------------------------

def vwap_rsi(bars: list[Bar], cfg: dict = None) -> StrategyOutput:
    cfg = cfg or {}
    rsi_buy = cfg.get("rsiBuy", 55)
    rsi_sell = cfg.get("rsiSell", 45)
    sl_pct = cfg.get("slPct", 0.01)
    rr = cfg.get("rr", 2)

    ind = compute_indicators(bars)
    px = bars[-1].c
    above = px > ind.vwap
    vol_ok = ind.relVolume >= 1.1

    if above and ind.rsi >= rsi_buy and ind.rsi <= 72 and vol_ok:
        stop = min(px * (1 - sl_pct), ind.vwap * 0.997)
        return _base(
            "vwap_rsi", "v1", "BUY",
            entry=px, stop=stop, target=px + (px - stop) * rr,
            confidence=min(0.84, 0.48 + (ind.relVolume - 1) * 0.15 + (ind.rsi - 50) / 120),
            reason=f"Price {(px / ind.vwap - 1) * 100:.2f}% above VWAP, RSI {ind.rsi:.0f}, rel volume {ind.relVolume:.2f}.",
            invalidation="VWAP breakdown or RSI rolling over through 50.",
            metadata={"vwap": ind.vwap, "rsi": ind.rsi, "relVolume": ind.relVolume},
        )

    if not above and ind.rsi <= rsi_sell and ind.rsi >= 28 and vol_ok:
        stop = max(px * (1 + sl_pct), ind.vwap * 1.003)
        return _base(
            "vwap_rsi", "v1", "SELL",
            entry=px, stop=stop, target=px - (stop - px) * rr,
            confidence=min(0.82, 0.48 + (ind.relVolume - 1) * 0.15 + (50 - ind.rsi) / 120),
            reason=f"Price below VWAP, RSI {ind.rsi:.0f}, volume confirmation {ind.relVolume:.2f}.",
            invalidation="Reclaim of VWAP or RSI crossing 50.",
            metadata={"vwap": ind.vwap, "rsi": ind.rsi, "relVolume": ind.relVolume},
        )

    if not vol_ok:
        return _base(
            "vwap_rsi", "v1", "SKIP",
            confidence=0.38,
            reason=f"Relative volume {ind.relVolume:.2f} is thin. VWAP breaks without volume are usually faded.",
            invalidation="Rel volume > 1.1 with VWAP side confirmed.",
            metadata={"relVolume": ind.relVolume, "rsi": ind.rsi},
        )

    return _base(
        "vwap_rsi", "v1", "HOLD",
        confidence=0.42,
        reason=f"RSI {ind.rsi:.0f} not in the continuation band relative to VWAP.",
        invalidation="RSI hold above 55 with price over VWAP (or the inverse).",
        metadata={"rsi": ind.rsi, "vwap": ind.vwap},
    )


# ---------------------------------------------------------------------------
# Opening Range Breakout (ORB)
# ---------------------------------------------------------------------------

def orb(bars: list[Bar], cfg: dict = None) -> StrategyOutput:
    cfg = cfg or {}
    or_bars = int(cfg.get("orBars", 3))
    sl_pct = cfg.get("slPct", 0.008)
    rr = cfg.get("rr", 1.5)

    if len(bars) < or_bars + 5:
        return _base(
            "orb", "v1", "SKIP",
            confidence=0.2,
            reason="Not enough bars to form an opening range.",
            invalidation="Wait for the opening range to complete.",
        )

    opening = bars[-20:-20 + or_bars] if len(bars) >= 20 else []
    window = opening if opening else bars[:or_bars]
    orh = max(b.h for b in window)
    orl = min(b.l for b in window)
    px = bars[-1].c
    ind = compute_indicators(bars)
    range_pct = (orh - orl) / ((orh + orl) / 2) if (orh + orl) > 0 else 0

    if range_pct > 0.025:
        return _base(
            "orb", "v1", "SKIP",
            confidence=0.33,
            reason=f"Opening range {range_pct * 100:.2f}% is too wide — breakouts here have poor R.",
            invalidation="A compressed opening range (< 1.5%).",
            metadata={"orh": orh, "orl": orl, "rangePct": range_pct},
        )

    if px > orh and ind.relVolume > 1.05:
        stop = max(orl, px * (1 - sl_pct))
        return _base(
            "orb", "v1", "BUY",
            entry=px, stop=stop, target=px + (px - stop) * rr,
            confidence=min(0.8, 0.5 + ind.relVolume * 0.1),
            reason=f"Break of opening-range high {orh:.2f} with rel volume {ind.relVolume:.2f}.",
            invalidation=f"Back inside the range or stop {stop:.2f}.",
            metadata={"orh": orh, "orl": orl, "relVolume": ind.relVolume},
        )

    if px < orl and ind.relVolume > 1.05:
        stop = min(orh, px * (1 + sl_pct))
        return _base(
            "orb", "v1", "SELL",
            entry=px, stop=stop, target=px - (stop - px) * rr,
            confidence=min(0.78, 0.5 + ind.relVolume * 0.1),
            reason=f"Break of opening-range low {orl:.2f} with volume.",
            invalidation=f"Back inside the range or stop {stop:.2f}.",
            metadata={"orh": orh, "orl": orl, "relVolume": ind.relVolume},
        )

    return _base(
        "orb", "v1", "HOLD",
        confidence=0.4,
        reason=f"Price still inside opening range {orl:.2f}\u2013{orh:.2f}.",
        invalidation="A volume-confirmed range break.",
        metadata={"orh": orh, "orl": orl},
    )


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------

STRATEGIES = [
    {"id": "ma_cross",  "version": "v1", "defaults": {"fast": 9, "slow": 21, "slPct": 0.01, "rr": 2},     "run": ma_cross},
    {"id": "vwap_rsi",  "version": "v1", "defaults": {"rsiBuy": 55, "rsiSell": 45, "slPct": 0.01, "rr": 2}, "run": vwap_rsi},
    {"id": "orb",       "version": "v1", "defaults": {"orBars": 3, "slPct": 0.008, "rr": 1.5},              "run": orb},
]

STRATEGY_BY_ID = {s["id"]: s for s in STRATEGIES}


def run_strategy(id_: str, bars: list[Bar], cfg: dict = None) -> StrategyOutput:
    defn = STRATEGY_BY_ID.get(id_)
    if defn is None:
        raise ValueError(f"Unknown strategy {id_}")
    merged = {**defn["defaults"], **(cfg or {})}
    return defn["run"](bars, merged)


def run_all_strategies(bars: list[Bar]) -> list[StrategyOutput]:
    return [s["run"](bars, s["defaults"]) for s in STRATEGIES]
