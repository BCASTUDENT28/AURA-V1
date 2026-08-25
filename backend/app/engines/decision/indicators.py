"""
backend/app/engines/decision/indicators.py

Port of src/lib/aura/indicators.ts
All algorithms kept identical so Python produces the same floats as TypeScript
(within floating-point precision — tolerance in parity tests is 1e-6).
"""

from __future__ import annotations

import math

from backend.app.schemas.types import Bar, Indicators


def _sma(xs: list[float], n: int) -> float:
    if len(xs) < n:
        return xs[-1] if xs else 0.0
    return sum(xs[-n:]) / n


def _ema(xs: list[float], n: int) -> float:
    if not xs:
        return 0.0
    k = 2.0 / (n + 1)
    e = xs[0]
    for x in xs[1:]:
        e = x * k + e * (1 - k)
    return e


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    v = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(v)


def rsi(closes: list[float], n: int = 14) -> float:
    if len(closes) < n + 1:
        return 50.0
    gain = 0.0
    loss = 0.0
    for i in range(len(closes) - n, len(closes)):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gain += d
        else:
            loss -= d
    ag = gain / n
    al = loss / n
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1 + rs)


def atr(bars: list[Bar], n: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(bars)):
        b = bars[i]
        p = bars[i - 1]
        trs.append(max(b.h - b.l, abs(b.h - p.c), abs(b.l - p.c)))
    return _sma(trs, min(n, len(trs)))


def adx_pack(bars: list[Bar], n: int = 14) -> dict:
    if len(bars) < n + 2:
        return {"adx": 15.0, "plusDi": 20.0, "minusDi": 20.0}
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    tr: list[float] = []
    for i in range(1, len(bars)):
        b = bars[i]
        p = bars[i - 1]
        up = b.h - p.h
        down = p.l - b.l
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        tr.append(max(b.h - b.l, abs(b.h - p.c), abs(b.l - p.c)))
    tr_n = _sma(tr, n)
    p_n = _sma(plus_dm, n)
    m_n = _sma(minus_dm, n)
    plus_di = (100 * p_n / tr_n) if tr_n else 0.0
    minus_di = (100 * m_n / tr_n) if tr_n else 0.0
    denom = plus_di + minus_di
    dx = (100 * abs(plus_di - minus_di) / denom) if denom else 0.0
    return {"adx": dx, "plusDi": plus_di, "minusDi": minus_di}


def macd_pack(closes: list[float]) -> dict:
    macd_val = _ema(closes, 12) - _ema(closes, 26)
    # replicate TS: compute rolling macd series then ema(series, 9)
    series: list[float] = []
    e12 = closes[0] if closes else 0.0
    e26 = closes[0] if closes else 0.0
    k12 = 2.0 / 13
    k26 = 2.0 / 27
    for c in closes:
        e12 = c * k12 + e12 * (1 - k12)
        e26 = c * k26 + e26 * (1 - k26)
        series.append(e12 - e26)
    return {"macd": macd_val, "signal": _ema(series, 9)}


def vwap(bars: list[Bar], lookback: int = 20) -> float:
    sl = bars[-lookback:]
    pv = 0.0
    vv = 0.0
    for b in sl:
        tp = (b.h + b.l + b.c) / 3
        pv += tp * b.v
        vv += b.v
    if vv:
        return pv / vv
    return sl[-1].c if sl else 0.0


def realized_vol(closes: list[float], n: int = 20) -> float:
    if len(closes) < n + 1:
        return 0.15
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - n, len(closes))]
    return _stdev(rets) * math.sqrt(252)


def compute_indicators(bars: list[Bar]) -> Indicators:
    closes = [b.c for b in bars]
    vols = [b.v for b in bars]
    adx_data = adx_pack(bars)
    macd_data = macd_pack(closes)
    mid = _sma(closes, 20)
    sd = _stdev(closes[-20:])
    avg_vol = _sma(vols, 20)
    last_vol = vols[-1] if vols else 0.0
    vol_slice = vols[-20:]
    vol_stdev = _stdev(vol_slice) if vol_slice else 1.0
    vz = (last_vol - avg_vol) / (vol_stdev or 1.0) if sd and vol_slice else 0.0
    rel_volume = last_vol / avg_vol if avg_vol else 1.0

    return Indicators(
        smaFast=_sma(closes, 9),
        smaSlow=_sma(closes, 21),
        ema9=_ema(closes, 9),
        ema21=_ema(closes, 21),
        rsi=rsi(closes, 14),
        macd=macd_data["macd"],
        macdSignal=macd_data["signal"],
        atr=atr(bars, 14),
        adx=adx_data["adx"],
        plusDi=adx_data["plusDi"],
        minusDi=adx_data["minusDi"],
        vwap=vwap(bars, 20),
        bbUpper=mid + 2 * sd,
        bbLower=mid - 2 * sd,
        bbMid=mid,
        realizedVol=realized_vol(closes, 20),
        volumeZ=vz,
        relVolume=rel_volume,
    )
