"""
backend/app/data/simulator.py

Port of src/lib/aura/rng.ts + src/lib/aura/market.ts
The RNG algorithm (mulberry32 + hashString) and all market-generation
parameters are kept bit-for-bit identical to the TypeScript originals
so that the parity tests pass.

⚠️  This is the authoritative backend data source.
    The frontend must not generate its own bars/quotes.
"""

from __future__ import annotations

import math
from typing import Optional

from backend.app.schemas.types import Bar, Instrument, Quote, RegimeLabel

# ---------------------------------------------------------------------------
# RNG: Mulberry32 + FNV-1a hashString  (mirrors rng.ts exactly)
# ---------------------------------------------------------------------------

_U32 = 0xFFFFFFFF


def _imul32(a: int, b: int) -> int:
    """JavaScript Math.imul — 32-bit signed multiply."""
    a = a & _U32
    b = b & _U32
    result = (a * b) & _U32
    # Sign-extend if high bit set
    if result >= 0x80000000:
        result -= 0x100000000
    return result


def hash_string(s: str) -> int:
    """FNV-1a hash, mirrors TypeScript hashString() → unsigned 32-bit int."""
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = _imul32(h, 16777619) & _U32
    return h & _U32


def mulberry32(seed: int):
    """
    Closure factory — mirrors TypeScript mulberry32().
    Returns a callable that yields floats in [0, 1).
    """
    a = [seed & _U32]  # mutable cell

    def next_val() -> float:
        a[0] = (a[0] | 0) & _U32
        a[0] = (a[0] + 0x6D2B79F5) & _U32
        # Ensure signed arithmetic matching JS `| 0`
        av = a[0] if a[0] < 0x80000000 else a[0] - 0x100000000

        t = _imul32(av ^ ((a[0] >> 15) & _U32), 1 | a[0])
        t32 = t & _U32
        t_val = t32 if t32 < 0x80000000 else t32 - 0x100000000

        t_val2 = (t_val + _imul32(t_val ^ ((t32 >> 7) & _U32), 61 | t32)) ^ t_val
        t2_u32 = t_val2 & _U32

        return ((t2_u32 ^ ((t2_u32 >> 14) & _U32)) & _U32) / 4294967296.0

    return next_val


def gaussian(rng) -> float:
    """Box-Muller transform — mirrors TypeScript gaussian()."""
    u, v = 0.0, 0.0
    while u == 0.0:
        u = rng()
    while v == 0.0:
        v = rng()
    return math.sqrt(-2.0 * math.log(u)) * math.cos(2.0 * math.pi * v)


# ---------------------------------------------------------------------------
# Instruments (mirrors instruments.ts — used for hash seeds)
# ---------------------------------------------------------------------------

INSTRUMENTS: list[Instrument] = [
    Instrument(symbol="NIFTY",      name="Nifty 50",              sector="Index",   kind="index",  base=24862, tick=0.05, lot=1, avgVolume=2.4e8),
    Instrument(symbol="BANKNIFTY",  name="Nifty Bank",            sector="Index",   kind="index",  base=51240, tick=0.05, lot=1, avgVolume=8.1e7),
    Instrument(symbol="RELIANCE",   name="Reliance Industries",   sector="Energy",  kind="equity", base=1478,  tick=0.05, lot=1, avgVolume=6.2e6),
    Instrument(symbol="TCS",        name="Tata Consultancy",      sector="IT",      kind="equity", base=4124,  tick=0.05, lot=1, avgVolume=2.1e6),
    Instrument(symbol="HDFCBANK",   name="HDFC Bank",             sector="Banks",   kind="equity", base=1682,  tick=0.05, lot=1, avgVolume=1.4e7),
    Instrument(symbol="INFY",       name="Infosys",               sector="IT",      kind="equity", base=1786,  tick=0.05, lot=1, avgVolume=6.8e6),
    Instrument(symbol="ICICIBANK",  name="ICICI Bank",            sector="Banks",   kind="equity", base=1284,  tick=0.05, lot=1, avgVolume=1.1e7),
    Instrument(symbol="HINDUNILVR", name="Hindustan Unilever",    sector="FMCG",   kind="equity", base=2488,  tick=0.05, lot=1, avgVolume=1.4e6),
    Instrument(symbol="ITC",        name="ITC",                   sector="FMCG",   kind="equity", base=492,   tick=0.05, lot=1, avgVolume=1.2e7),
    Instrument(symbol="SBIN",       name="State Bank of India",   sector="Banks",   kind="equity", base=812,   tick=0.05, lot=1, avgVolume=1.5e7),
    Instrument(symbol="BHARTIARTL", name="Bharti Airtel",         sector="Telecom", kind="equity", base=1648,  tick=0.05, lot=1, avgVolume=5.4e6),
    Instrument(symbol="BAJFINANCE", name="Bajaj Finance",         sector="Finance", kind="equity", base=9120,  tick=0.05, lot=1, avgVolume=9.2e5),
    Instrument(symbol="LT",         name="Larsen & Toubro",       sector="Infra",   kind="equity", base=3584,  tick=0.05, lot=1, avgVolume=1.8e6),
    Instrument(symbol="HCLTECH",    name="HCL Technologies",      sector="IT",      kind="equity", base=1688,  tick=0.05, lot=1, avgVolume=3.2e6),
    Instrument(symbol="AXISBANK",   name="Axis Bank",             sector="Banks",   kind="equity", base=1124,  tick=0.05, lot=1, avgVolume=8.4e6),
    Instrument(symbol="ASIANPAINT", name="Asian Paints",          sector="FMCG",   kind="equity", base=2486,  tick=0.05, lot=1, avgVolume=1.1e6),
    Instrument(symbol="MARUTI",     name="Maruti Suzuki",         sector="Auto",    kind="equity", base=12480, tick=0.05, lot=1, avgVolume=4.8e5),
    Instrument(symbol="SUNPHARMA",  name="Sun Pharma",            sector="Pharma",  kind="equity", base=1722,  tick=0.05, lot=1, avgVolume=2.4e6),
    Instrument(symbol="TITAN",      name="Titan Company",         sector="Consumer",kind="equity", base=3488,  tick=0.05, lot=1, avgVolume=1.2e6),
    Instrument(symbol="ULTRACEMCO", name="UltraTech Cement",      sector="Cement",  kind="equity", base=11840, tick=0.05, lot=1, avgVolume=3.6e5),
    Instrument(symbol="M&M",        name="Mahindra & Mahindra",   sector="Auto",    kind="equity", base=2784,  tick=0.05, lot=1, avgVolume=2.8e6),
    Instrument(symbol="TATAMOTORS", name="Tata Motors",           sector="Auto",    kind="equity", base=784,   tick=0.05, lot=1, avgVolume=1.4e7),
    Instrument(symbol="TATASTEEL",  name="Tata Steel",            sector="Metals",  kind="equity", base=154,   tick=0.05, lot=1, avgVolume=2.8e7),
    Instrument(symbol="NTPC",       name="NTPC",                  sector="Energy",  kind="equity", base=412,   tick=0.05, lot=1, avgVolume=1.1e7),
    Instrument(symbol="POWERGRID",  name="Power Grid",            sector="Energy",  kind="equity", base=328,   tick=0.05, lot=1, avgVolume=9.4e6),
    Instrument(symbol="ONGC",       name="ONGC",                  sector="Energy",  kind="equity", base=268,   tick=0.05, lot=1, avgVolume=1.6e7),
    Instrument(symbol="WIPRO",      name="Wipro",                 sector="IT",      kind="equity", base=512,   tick=0.05, lot=1, avgVolume=7.2e6),
    Instrument(symbol="CIPLA",      name="Cipla",                 sector="Pharma",  kind="equity", base=1548,  tick=0.05, lot=1, avgVolume=1.6e6),
    Instrument(symbol="DRREDDY",    name="Dr. Reddy's",           sector="Pharma",  kind="equity", base=1284,  tick=0.05, lot=1, avgVolume=8.4e5),
    Instrument(symbol="JSWSTEEL",   name="JSW Steel",             sector="Metals",  kind="equity", base=968,   tick=0.05, lot=1, avgVolume=4.2e6),
]

BY_SYMBOL: dict[str, Instrument] = {i.symbol: i for i in INSTRUMENTS}


def get_instrument(symbol: str) -> Instrument:
    inst = BY_SYMBOL.get(symbol)
    if inst is None:
        raise ValueError(f"Unknown instrument {symbol}")
    return inst


# ---------------------------------------------------------------------------
# Market simulation constants (mirrors market.ts)
# ---------------------------------------------------------------------------

SESSION_END = 1755216000000   # Date.UTC(2026, 7, 21, 10, 0, 0) — Mon 21 Aug 2026 10:00 UTC = 15:30 IST
PAPER_OPEN  = 1755390300000   # Date.UTC(2026, 7, 24, 3, 45, 0) — Mon 24 Aug 2026 09:15 IST
DAILY_BARS  = 520
MINUTE_BARS = 75 * 8          # ~8 sessions of 5m

REGIME_PARAMS: dict[str, dict] = {
    "BULL_TREND":  {"mu":  0.00055, "sigma": 0.009},
    "BEAR_TREND":  {"mu": -0.00045, "sigma": 0.012},
    "RANGE":       {"mu":  0.00002, "sigma": 0.007},
    "HIGH_VOL":    {"mu":  0.0,     "sigma": 0.018},
    "LOW_VOL":     {"mu":  0.00015, "sigma": 0.0045},
    "BREAKOUT":    {"mu":  0.0008,  "sigma": 0.014},
    "MEAN_REVERT": {"mu":  0.0,     "sigma": 0.008},
    "STRESS":      {"mu": -0.0012,  "sigma": 0.028},
}

_REGIME_KEYS: list[str] = list(REGIME_PARAMS.keys())


def _next_regime(rng, current: str) -> str:
    if rng() > 0.018:
        return current
    return _REGIME_KEYS[int(rng() * len(_REGIME_KEYS)) % len(_REGIME_KEYS)]


def _round_tick(px: float, tick: float) -> float:
    return max(tick, round(px / tick) * tick)


def _make_bar(t: int, prev: float, ret: float, rng, inst: Instrument, vol_mult: float) -> Bar:
    c = _round_tick(prev * (1 + ret), inst.tick)
    wick = abs(ret) + abs(gaussian(rng)) * 0.004
    h = _round_tick(max(prev, c) * (1 + wick * (0.3 + rng() * 0.7)), inst.tick)
    l = _round_tick(min(prev, c) * (1 - wick * (0.3 + rng() * 0.7)), inst.tick)
    o = _round_tick(prev * (1 + (rng() - 0.5) * abs(ret) * 0.6), inst.tick)
    hi = max(o, h, c)
    lo = min(o, l, c)
    v = max(1, round(inst.avgVolume * vol_mult * (0.55 + rng() * 0.9)))
    return Bar(t=t, o=o, h=hi, l=lo, c=c, v=v)


# ---------------------------------------------------------------------------
# Daily series generation (mirrors generateDaily in market.ts)
# ---------------------------------------------------------------------------

def _generate_daily(inst: Instrument, end: int) -> tuple[list[Bar], list[str]]:
    rng = mulberry32(hash_string(f"d:{inst.symbol}:v4"))
    label: str = "BULL_TREND" if inst.kind == "index" else "RANGE"
    px = inst.base * (0.72 + rng() * 0.12)
    bars: list[Bar] = []
    regimes: list[str] = []
    t = end - DAILY_BARS * 86_400_000
    i = 0
    while i < DAILY_BARS:
        # skip weekends (UTC day: 0=Sun, 6=Sat)
        import datetime
        day = datetime.datetime.fromtimestamp(t / 1000, tz=datetime.timezone.utc).weekday()  # Mon=0..Sun=6
        # Python weekday(): 0=Mon,...,6=Sun → JS equiv: (weekday+1)%7 gives 0=Sun,6=Sat
        js_day_equiv = (day + 1) % 7
        if js_day_equiv == 0 or js_day_equiv == 6:  # Sun=0, Sat=6
            t += 86_400_000
            continue
        label = _next_regime(rng, label)
        p = REGIME_PARAMS[label]
        beta = 1.0 if inst.kind == "index" else 0.7 + rng() * 0.6
        ret = (p["mu"] + p["sigma"] * gaussian(rng)) * beta
        vol_mult = 1.8 if label in ("STRESS", "HIGH_VOL") else 1.0
        bars.append(_make_bar(t + 10 * 3_600_000, px, ret, rng, inst, vol_mult))
        regimes.append(label)
        px = bars[-1].c
        t += 86_400_000
        i += 1

    # pin last close near advertised base
    last = bars[-1]
    scale = inst.base / last.c if last.c != 0 else 1.0
    if math.isfinite(scale) and scale > 0 and abs(scale - 1) > 0.002:
        updated: list[Bar] = []
        for b in bars:
            bo = _round_tick(b.o * scale, inst.tick)
            bh = _round_tick(b.h * scale, inst.tick)
            bl = _round_tick(b.l * scale, inst.tick)
            bc = _round_tick(b.c * scale, inst.tick)
            if bh < bl:
                bh, bl = bl, bh
            bh = max(bh, bo, bc)
            bl = min(bl, bo, bc)
            updated.append(Bar(t=b.t, o=bo, h=bh, l=bl, c=bc, v=b.v))
        bars = updated

    return bars, regimes


# ---------------------------------------------------------------------------
# Minute series generation (mirrors generateMinute in market.ts)
# ---------------------------------------------------------------------------

def _generate_minute(inst: Instrument, daily: list[Bar]) -> list[Bar]:
    rng = mulberry32(hash_string(f"m:{inst.symbol}:v4"))
    last_days = daily[-8:]
    out: list[Bar] = []
    for d in last_days:
        px = d.o
        session_open = d.t - 10 * 3_600_000 + (3 * 3_600_000 + 45 * 60_000)
        day_ret = (d.c - d.o) / d.o if d.o != 0 else 0
        for i in range(75):
            t = session_open + i * 5 * 60_000
            drift = day_ret / 75
            ret = drift + gaussian(rng) * 0.0018
            vol_mult = 1.6 if (i < 6 or i > 68) else 0.85
            bar = _make_bar(t, px, ret, rng, inst, vol_mult / 75)
            out.append(bar)
            px = bar.c
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SeriesPack:
    def __init__(self, daily: list[Bar], minute: list[Bar], regimes: list[str]):
        self.daily = daily
        self.minute = minute
        self.regimes = regimes


class MarketUniverse:
    def __init__(self, series: dict[str, SeriesPack]):
        self.series = series
        self.quality = {
            "source": "AURA simulator / corporate-action adjusted",
            "generatedAt": SESSION_END,
            "missingCandles": 0,
            "duplicates": 0,
            "corporateActionsApplied": 4,
            "timezone": "Asia/Kolkata",
            "status": "PASS",
            "datasetVersion": "sim-in-eq-20240821",
        }


_cached_universe: Optional[MarketUniverse] = None


def get_universe() -> MarketUniverse:
    global _cached_universe
    if _cached_universe is not None:
        return _cached_universe
    series: dict[str, SeriesPack] = {}
    for inst in INSTRUMENTS:
        daily, regimes = _generate_daily(inst, SESSION_END)
        minute = _generate_minute(inst, daily)
        series[inst.symbol] = SeriesPack(daily=daily, minute=minute, regimes=regimes)
    _cached_universe = MarketUniverse(series=series)
    return _cached_universe


def bars_of(symbol: str, tf: str = "1D") -> list[Bar]:
    s = get_universe().series.get(symbol)
    if s is None:
        raise ValueError(f"Unknown symbol {symbol}")
    return s.daily if tf == "1D" else s.minute


def last_bar(symbol: str, tf: str = "1D") -> Bar:
    return bars_of(symbol, tf)[-1]


def quote_from(symbol: str, ltp: float, prev: Bar, ts: int, volume: float) -> Quote:
    change = ltp - prev.c
    spread = max(0.05, ltp * 0.00015)
    return Quote(
        symbol=symbol,
        ltp=ltp,
        bid=_round_tick(ltp - spread / 2, 0.05),
        ask=_round_tick(ltp + spread / 2, 0.05),
        open=prev.o,
        high=max(prev.h, ltp),
        low=min(prev.l, ltp),
        prevClose=prev.c,
        change=change,
        changePct=change / prev.c if prev.c != 0 else 0,
        volume=volume,
        ts=ts,
    )


def seed_quotes(now: int) -> dict[str, Quote]:
    out: dict[str, Quote] = {}
    for inst in INSTRUMENTS:
        daily = bars_of(inst.symbol, "1D")
        last = daily[-1]
        prev = daily[-2] if len(daily) >= 2 else last
        change = last.c - prev.c
        spread = max(0.05, last.c * 0.00015)
        out[inst.symbol] = Quote(
            symbol=inst.symbol,
            ltp=last.c,
            bid=_round_tick(last.c - spread / 2, 0.05),
            ask=_round_tick(last.c + spread / 2, 0.05),
            open=last.o,
            high=last.h,
            low=last.l,
            prevClose=prev.c,
            change=change,
            changePct=change / prev.c if prev.c != 0 else 0,
            volume=last.v,
            ts=now,
        )
    return out


def quotes_now() -> dict[str, Quote]:
    import time
    return seed_quotes(int(time.time() * 1000))

