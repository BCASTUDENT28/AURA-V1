"""
backend/app/quant/features.py

Unified Quant Feature Pack for AURA AI.
Shared across:
- Real-time decision engine
- Research & backtesting laboratory
- ML training and inference pipelines

Guarantees:
- Strict no-lookahead computation (feature at index t depends ONLY on bars <= t).
- High precision float calculations with NaN/Inf protection.
"""

from __future__ import annotations

import math
from typing import Optional
from pydantic import BaseModel
from backend.app.schemas.types import Bar


class FeatureVector(BaseModel):
    # Timestamps & Prices
    t: int
    close: float

    # Trend & Moving Averages
    sma9: float
    sma21: float
    sma50: float
    sma200: float
    ema9: float
    ema21: float
    ema50: float

    # Momentum & Oscillators
    rsi14: float
    macd: float
    macdSignal: float
    macdHist: float

    # Volatility & Bands
    atr14: float
    adx14: float
    plusDi14: float
    minusDi14: float
    bbUpper: float
    bbLower: float
    bbMid: float
    bbPercentB: float
    bbBandwidth: float
    realizedVol20: float

    # Volume & Intraday
    vwap20: float
    vwapDevAtr: float
    volumeZ20: float
    relVolume20: float

    # Statistical / Return Features
    return1d: float
    return5d: float
    return20d: float
    skewness20: float
    autocorr1: float


def _sma(xs: list[float], n: int) -> float:
    if not xs:
        return 0.0
    if len(xs) < n:
        return sum(xs) / len(xs)
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


def _rsi(closes: list[float], n: int = 14) -> float:
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
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(bars: list[Bar], n: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(bars)):
        b = bars[i]
        p = bars[i - 1]
        trs.append(max(b.h - b.l, abs(b.h - p.c), abs(b.l - p.c)))
    return _sma(trs, min(n, len(trs)))


def _adx(bars: list[Bar], n: int = 14) -> dict[str, float]:
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


def _macd(closes: list[float]) -> dict[str, float]:
    if not closes:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0}
    macd_val = _ema(closes, 12) - _ema(closes, 26)
    series: list[float] = []
    e12 = closes[0]
    e26 = closes[0]
    k12 = 2.0 / 13
    k26 = 2.0 / 27
    for c in closes:
        e12 = c * k12 + e12 * (1 - k12)
        e26 = c * k26 + e26 * (1 - k26)
        series.append(e12 - e26)
    signal = _ema(series, 9)
    return {"macd": macd_val, "signal": signal, "hist": macd_val - signal}


def _vwap(bars: list[Bar], lookback: int = 20) -> float:
    sl = bars[-lookback:] if len(bars) >= lookback else bars
    pv = 0.0
    vv = 0.0
    for b in sl:
        tp = (b.h + b.l + b.c) / 3.0
        pv += tp * b.v
        vv += b.v
    if vv > 0:
        return pv / vv
    return sl[-1].c if sl else 0.0


def _skewness(xs: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    m = sum(xs) / n
    sd = _stdev(xs)
    if sd == 0:
        return 0.0
    return (sum((x - m) ** 3 for x in xs) / n) / (sd ** 3)


def _autocorr_lag1(xs: list[float]) -> float:
    if len(xs) < 3:
        return 0.0
    x_t = xs[1:]
    x_t_1 = xs[:-1]
    m1 = sum(x_t) / len(x_t)
    m2 = sum(x_t_1) / len(x_t_1)
    cov = sum((a - m1) * (b - m2) for a, b in zip(x_t, x_t_1)) / len(x_t)
    s1 = _stdev(x_t)
    s2 = _stdev(x_t_1)
    if s1 * s2 == 0:
        return 0.0
    return cov / (s1 * s2)


def extract_features(bars: list[Bar]) -> FeatureVector:
    """
    Compute full quantitative feature pack for a candle series.
    Strictly causal: does not use any information past bars[-1].
    """
    if not bars:
        raise ValueError("Cannot extract features from empty bar list.")

    closes = [b.c for b in bars]
    vols = [b.v for b in bars]
    last_bar = bars[-1]
    px = last_bar.c

    # Moving averages
    s9 = _sma(closes, 9)
    s21 = _sma(closes, 21)
    s50 = _sma(closes, 50)
    s200 = _sma(closes, 200)
    e9 = _ema(closes, 9)
    e21 = _ema(closes, 21)
    e50 = _ema(closes, 50)

    # Momentum
    rsi_val = _rsi(closes, 14)
    macd_pack = _macd(closes)

    # Volatility
    atr_val = _atr(bars, 14)
    adx_pack = _adx(bars, 14)
    mid20 = _sma(closes, 20)
    sd20 = _stdev(closes[-20:])
    bb_upper = mid20 + 2.0 * sd20
    bb_lower = mid20 - 2.0 * sd20
    bb_pct_b = (px - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
    bb_bandwidth = (bb_upper - bb_lower) / mid20 if mid20 > 0 else 0.0

    # Realized volatility (20d annualized log returns)
    if len(closes) >= 21:
        log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 20, len(closes)) if closes[i - 1] > 0]
        realized_vol = _stdev(log_rets) * math.sqrt(252)
    else:
        log_rets = []
        realized_vol = 0.15

    # Volume & VWAP
    vwap_val = _vwap(bars, 20)
    denom_atr = atr_val if atr_val > 0 else (px * 0.01)
    vwap_dev_atr = (px - vwap_val) / denom_atr

    avg_vol20 = _sma(vols, 20)
    sd_vol20 = _stdev(vols[-20:]) if len(vols) >= 20 else 1.0
    vol_z = (last_bar.v - avg_vol20) / sd_vol20 if sd_vol20 > 0 else 0.0
    rel_vol = last_bar.v / avg_vol20 if avg_vol20 > 0 else 1.0

    # Returns
    p1 = closes[-2] if len(closes) >= 2 else px
    p5 = closes[-6] if len(closes) >= 6 else px
    p20 = closes[-21] if len(closes) >= 21 else px
    ret1d = (px - p1) / p1 if p1 > 0 else 0.0
    ret5d = (px - p5) / p5 if p5 > 0 else 0.0
    ret20d = (px - p20) / p20 if p20 > 0 else 0.0

    # Skewness and autocorrelation of returns
    skew = _skewness(log_rets) if len(log_rets) >= 5 else 0.0
    autocorr = _autocorr_lag1(log_rets) if len(log_rets) >= 5 else 0.0

    return FeatureVector(
        t=last_bar.t,
        close=px,
        sma9=round(s9, 4),
        sma21=round(s21, 4),
        sma50=round(s50, 4),
        sma200=round(s200, 4),
        ema9=round(e9, 4),
        ema21=round(e21, 4),
        ema50=round(e50, 4),
        rsi14=round(rsi_val, 4),
        macd=round(macd_pack["macd"], 4),
        macdSignal=round(macd_pack["signal"], 4),
        macdHist=round(macd_pack["hist"], 4),
        atr14=round(atr_val, 4),
        adx14=round(adx_pack["adx"], 4),
        plusDi14=round(adx_pack["plusDi"], 4),
        minusDi14=round(adx_pack["minusDi"], 4),
        bbUpper=round(bb_upper, 4),
        bbLower=round(bb_lower, 4),
        bbMid=round(mid20, 4),
        bbPercentB=round(bb_pct_b, 4),
        bbBandwidth=round(bb_bandwidth, 4),
        realizedVol20=round(realized_vol, 4),
        vwap20=round(vwap_val, 4),
        vwapDevAtr=round(vwap_dev_atr, 4),
        volumeZ20=round(vol_z, 4),
        relVolume20=round(rel_vol, 4),
        return1d=round(ret1d, 6),
        return5d=round(ret5d, 6),
        return20d=round(ret20d, 6),
        skewness20=round(skew, 4),
        autocorr1=round(autocorr, 4),
    )


def extract_feature_matrix(bars: list[Bar], min_warmup: int = 50) -> list[FeatureVector]:
    """
    Extract a causal feature matrix over a rolling historical series.
    Ensures bar[i] is evaluated with strictly bars[:i+1].
    """
    if len(bars) < min_warmup:
        return [extract_features(bars)]
    matrix: list[FeatureVector] = []
    for i in range(min_warmup, len(bars) + 1):
        window = bars[:i]
        matrix.append(extract_features(window))
    return matrix
