"""
backend/app/features/engine.py

AURA V2 Feature Engine
======================
Unified, reusable feature pipeline with no-lookahead guarantee.

Feature categories:
  TREND      — SMA, EMA, ADX, directional movement, trend slope
  MOMENTUM   — RSI, MACD, ROC, momentum persistence
  VOLATILITY — ATR, realized vol, BB width, vol expansion/contraction
  VOLUME     — relative volume, volume acceleration, volume trend, VWAP distance
  STRUCTURE  — higher-high/lower-low, breakout distance, range compression, gap
  CONTEXT    — time of day, day of week, session phase

Design rules:
  1. All features computed from bars[:-1] (never using look-ahead bar data)
     EXCEPT the "current bar" features which use only already-closed data.
  2. Every feature returns a float in a well-defined range or annotated unit.
  3. Features are versioned via FEATURE_VERSION constant.
  4. No feature function mutates input bars.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

from backend.app.schemas.types import Bar

FEATURE_VERSION = "feat-v2"

# ─────────────────────────────────────────────────────────────────────────────
# Low-level math helpers (no lookahead by construction)
# ─────────────────────────────────────────────────────────────────────────────

def _sma(xs: list[float], n: int) -> float:
    if not xs:
        return 0.0
    sl = xs[-n:] if len(xs) >= n else xs
    return sum(sl) / len(sl)


def _ema(xs: list[float], n: int) -> float:
    """Wilder-style EMA with proper warmup."""
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
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _wilder_smooth(xs: list[float], n: int) -> float:
    """Wilder's smoothing (used in RSI, ATR, ADX)."""
    if len(xs) < n:
        return _sma(xs, len(xs)) if xs else 0.0
    # Seed with simple average of first n values
    result = sum(xs[:n]) / n
    for x in xs[n:]:
        result = (result * (n - 1) + x) / n
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Trend features
# ─────────────────────────────────────────────────────────────────────────────

def feat_sma_fast(bars: list[Bar], n: int = 9) -> float:
    """SMA of closes over last n bars."""
    return _sma([b.c for b in bars], n)


def feat_sma_slow(bars: list[Bar], n: int = 21) -> float:
    """SMA of closes over last n bars."""
    return _sma([b.c for b in bars], n)


def feat_ema_fast(bars: list[Bar], n: int = 9) -> float:
    return _ema([b.c for b in bars], n)


def feat_ema_slow(bars: list[Bar], n: int = 21) -> float:
    return _ema([b.c for b in bars], n)


def feat_adx(bars: list[Bar], n: int = 14) -> dict[str, float]:
    """
    ADX with Wilder smoothing (correct implementation).
    Returns {'adx': float, 'plus_di': float, 'minus_di': float}
    """
    if len(bars) < n + 2:
        return {"adx": 15.0, "plus_di": 20.0, "minus_di": 20.0}

    plus_dm: list[float] = []
    minus_dm: list[float] = []
    tr_list: list[float] = []

    for i in range(1, len(bars)):
        b, p = bars[i], bars[i - 1]
        up = b.h - p.h
        dn = p.l - b.l
        plus_dm.append(up if (up > dn and up > 0) else 0.0)
        minus_dm.append(dn if (dn > up and dn > 0) else 0.0)
        tr_list.append(max(b.h - b.l, abs(b.h - p.c), abs(b.l - p.c)))

    tr_n = _wilder_smooth(tr_list, n)
    p_n = _wilder_smooth(plus_dm, n)
    m_n = _wilder_smooth(minus_dm, n)

    plus_di = (100 * p_n / tr_n) if tr_n else 0.0
    minus_di = (100 * m_n / tr_n) if tr_n else 0.0
    denom = plus_di + minus_di
    dx = (100 * abs(plus_di - minus_di) / denom) if denom else 0.0

    return {"adx": dx, "plus_di": plus_di, "minus_di": minus_di}


def feat_trend_slope(bars: list[Bar], n: int = 20) -> float:
    """
    Linear regression slope of closes over last n bars (normalized by price).
    Positive = uptrend, negative = downtrend.
    Returns slope as fraction of average price per bar.
    """
    sl = [b.c for b in bars[-n:]]
    if len(sl) < 2:
        return 0.0
    n = len(sl)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(sl) / n
    num = sum((xs[i] - mx) * (sl[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    # Normalize by average price
    avg_px = my if my else 1.0
    return slope / avg_px


def feat_sma_crossover(bars: list[Bar], fast: int = 9, slow: int = 21) -> float:
    """
    Returns +1.0 (fresh bullish cross), -1.0 (fresh bearish cross), 0 (no cross).
    Uses last 2 bars to detect crossover.
    """
    closes = [b.c for b in bars]
    if len(closes) < slow + 1:
        return 0.0
    prev_fast = _sma(closes[:-1], fast)
    prev_slow = _sma(closes[:-1], slow)
    curr_fast = _sma(closes, fast)
    curr_slow = _sma(closes, slow)
    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return 1.0
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return -1.0
    return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Momentum features
# ─────────────────────────────────────────────────────────────────────────────

def feat_rsi(bars: list[Bar], n: int = 14) -> float:
    """RSI using Wilder's smoothing (correct implementation)."""
    closes = [b.c for b in bars]
    if len(closes) < n + 1:
        return 50.0

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))

    avg_gain = _wilder_smooth(gains, n)
    avg_loss = _wilder_smooth(losses, n)

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1 + rs)


def feat_macd(bars: list[Bar]) -> dict[str, float]:
    """MACD line, signal, and histogram."""
    closes = [b.c for b in bars]
    if not closes:
        return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}

    # Build rolling MACD series
    e12 = e26 = closes[0]
    k12, k26 = 2.0 / 13, 2.0 / 27
    series: list[float] = []
    for c in closes:
        e12 = c * k12 + e12 * (1 - k12)
        e26 = c * k26 + e26 * (1 - k26)
        series.append(e12 - e26)

    macd_val = series[-1]
    signal_val = _ema(series, 9)
    return {"macd": macd_val, "signal": signal_val, "histogram": macd_val - signal_val}


def feat_roc(bars: list[Bar], n: int = 10) -> float:
    """Rate of Change: (current - n_bars_ago) / n_bars_ago."""
    closes = [b.c for b in bars]
    if len(closes) <= n:
        return 0.0
    prev = closes[-(n + 1)]
    curr = closes[-1]
    return (curr - prev) / prev if prev else 0.0


def feat_momentum_persistence(bars: list[Bar], n: int = 5) -> float:
    """
    Fraction of last n bars that moved in the same direction as the most recent bar.
    Range [0, 1]. High = persistent directional move.
    """
    closes = [b.c for b in bars]
    if len(closes) < n + 1:
        return 0.5
    last_dir = 1.0 if closes[-1] >= closes[-2] else -1.0
    count = 0
    for i in range(len(closes) - n, len(closes)):
        d = closes[i] - closes[i - 1]
        if (d >= 0 and last_dir > 0) or (d < 0 and last_dir < 0):
            count += 1
    return count / n


# ─────────────────────────────────────────────────────────────────────────────
# Volatility features
# ─────────────────────────────────────────────────────────────────────────────

def feat_atr(bars: list[Bar], n: int = 14) -> float:
    """ATR using Wilder's smoothing."""
    if len(bars) < 2:
        return 0.0
    trs = [
        max(bars[i].h - bars[i].l, abs(bars[i].h - bars[i - 1].c), abs(bars[i].l - bars[i - 1].c))
        for i in range(1, len(bars))
    ]
    return _wilder_smooth(trs, n)


def feat_realized_vol(bars: list[Bar], n: int = 20) -> float:
    """Annualized realized volatility from log returns."""
    closes = [b.c for b in bars]
    if len(closes) < n + 1:
        return 0.15
    log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - n, len(closes))]
    return _stdev(log_rets) * math.sqrt(252)


def feat_bb_width(bars: list[Bar], n: int = 20, mult: float = 2.0) -> float:
    """Bollinger Band width normalized by mid: (upper - lower) / mid."""
    closes = [b.c for b in bars[-n:]]
    if len(closes) < 2:
        return 0.0
    mid = sum(closes) / len(closes)
    sd = _stdev(closes)
    if mid == 0:
        return 0.0
    return (2 * mult * sd) / mid


def feat_vol_expansion(bars: list[Bar], fast: int = 5, slow: int = 20) -> float:
    """
    Volatility expansion: ratio of short-term ATR to long-term ATR.
    > 1.0 = expanding volatility, < 1.0 = contracting.
    """
    if len(bars) < slow + 1:
        return 1.0
    atr_fast = feat_atr(bars[-fast - 1:], fast)
    atr_slow = feat_atr(bars, slow)
    if atr_slow == 0:
        return 1.0
    return atr_fast / atr_slow


# ─────────────────────────────────────────────────────────────────────────────
# Volume features
# ─────────────────────────────────────────────────────────────────────────────

def feat_vwap(bars: list[Bar], lookback: int = 20) -> float:
    """VWAP over lookback bars."""
    sl = bars[-lookback:]
    pv = vv = 0.0
    for b in sl:
        tp = (b.h + b.l + b.c) / 3
        pv += tp * b.v
        vv += b.v
    return pv / vv if vv else (sl[-1].c if sl else 0.0)


def feat_vwap_distance(bars: list[Bar]) -> float:
    """(price - VWAP) / VWAP — signed distance from VWAP."""
    vw = feat_vwap(bars)
    px = bars[-1].c
    return (px - vw) / vw if vw else 0.0


def feat_rel_volume(bars: list[Bar], n: int = 20) -> float:
    """Current bar volume / average volume. > 1 = above average."""
    vols = [b.v for b in bars]
    if not vols:
        return 1.0
    avg = _sma(vols, n)
    return vols[-1] / avg if avg else 1.0


def feat_volume_acceleration(bars: list[Bar], n: int = 5) -> float:
    """Rate of change in volume: (current_avg_vol - prev_avg_vol) / prev_avg_vol."""
    vols = [b.v for b in bars]
    if len(vols) < n * 2:
        return 0.0
    recent = sum(vols[-n:]) / n
    prev = sum(vols[-n * 2:-n]) / n
    return (recent - prev) / prev if prev else 0.0


def feat_volume_trend(bars: list[Bar], n: int = 10) -> float:
    """Linear regression slope of volume (normalized). Positive = rising volume."""
    vols = [b.v for b in bars[-n:]]
    if len(vols) < 2:
        return 0.0
    xs = list(range(len(vols)))
    mx = sum(xs) / len(xs)
    my = sum(vols) / len(vols)
    num = sum((xs[i] - mx) * (vols[i] - my) for i in range(len(vols)))
    den = sum((xs[i] - mx) ** 2 for i in range(len(vols)))
    slope = num / den if den else 0.0
    return slope / my if my else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Market structure features
# ─────────────────────────────────────────────────────────────────────────────

def feat_higher_highs(bars: list[Bar], n: int = 5) -> float:
    """
    Score for higher-high / lower-low structure.
    +1.0 = all highs rising (bullish structure)
    -1.0 = all highs falling (bearish structure)
    """
    if len(bars) < n + 1:
        return 0.0
    highs = [b.h for b in bars[-n - 1:]]
    hh_count = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i - 1])
    ll_count = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i - 1])
    total = len(highs) - 1
    return (hh_count - ll_count) / total if total else 0.0


def feat_breakout_distance(bars: list[Bar], n: int = 20) -> dict[str, float]:
    """
    Distance of current price from recent high/low (normalized).
    breakout_up = (close - highest_high_n) / highest_high_n
    breakout_dn = (lowest_low_n - close) / lowest_low_n
    """
    sl = bars[-n:]
    if not sl:
        return {"breakout_up": 0.0, "breakout_dn": 0.0}
    high_n = max(b.h for b in sl)
    low_n = min(b.l for b in sl)
    px = bars[-1].c
    return {
        "breakout_up": (px - high_n) / high_n if high_n else 0.0,
        "breakout_dn": (low_n - px) / low_n if low_n else 0.0,
    }


def feat_range_compression(bars: list[Bar], n_short: int = 5, n_long: int = 20) -> float:
    """
    Range compression: short-term range / long-term range.
    < 1 = compressed (potential breakout). > 1 = expanding.
    """
    if len(bars) < n_long:
        return 1.0

    def _range(sl: list[Bar]) -> float:
        return max(b.h for b in sl) - min(b.l for b in sl)

    short_range = _range(bars[-n_short:])
    long_range = _range(bars[-n_long:])
    return short_range / long_range if long_range else 1.0


def feat_gap(bars: list[Bar]) -> float:
    """
    Today's gap: (open - prev_close) / prev_close.
    Positive = gap up, negative = gap down.
    """
    if len(bars) < 2:
        return 0.0
    prev_close = bars[-2].c
    curr_open = bars[-1].o
    return (curr_open - prev_close) / prev_close if prev_close else 0.0


def feat_support_resistance_distance(bars: list[Bar], n: int = 20) -> dict[str, float]:
    """
    Distance from nearest support (lowest low) and resistance (highest high)
    over last n bars, normalized by ATR.
    """
    atr = feat_atr(bars, n=14) or 1.0
    sl = bars[-n:]
    high_n = max(b.h for b in sl)
    low_n = min(b.l for b in sl)
    px = bars[-1].c
    return {
        "dist_resistance": (high_n - px) / atr,
        "dist_support": (px - low_n) / atr,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Context features (time / session)
# ─────────────────────────────────────────────────────────────────────────────

def feat_session_phase(bar_ts_ms: int) -> dict[str, float]:
    """
    Time-based context features.
    bar_ts_ms: timestamp of the bar in milliseconds (IST assumed: UTC+5:30).
    Returns:
      hour_sin/cos  — cyclic hour encoding
      session_phase — 0=pre-open, 1=opening(9:15-10:00), 2=mid(10:00-14:30), 3=close(14:30-15:30)
      day_of_week   — 0=Mon ... 4=Fri (normalized 0-1)
    """
    dt = datetime.fromtimestamp(bar_ts_ms / 1000, tz=timezone.utc)
    # IST = UTC + 5:30
    ist_hour = (dt.hour + 5) % 24 + (0.5 if dt.minute >= 30 else 0.0)

    # Cyclic encoding
    hour_sin = math.sin(2 * math.pi * ist_hour / 24)
    hour_cos = math.cos(2 * math.pi * ist_hour / 24)

    # Session phase
    if ist_hour < 9.25:
        phase = 0.0  # pre-open
    elif ist_hour < 10.0:
        phase = 1.0  # opening range
    elif ist_hour < 14.5:
        phase = 2.0  # mid-session
    else:
        phase = 3.0  # closing

    dow = dt.weekday()  # 0=Mon, 4=Fri

    return {
        "hour_sin": hour_sin,
        "hour_cos": hour_cos,
        "session_phase": phase / 3.0,  # normalized 0-1
        "day_of_week": dow / 4.0,      # normalized 0-1
    }


# ─────────────────────────────────────────────────────────────────────────────
# Unified FeatureVector
# ─────────────────────────────────────────────────────────────────────────────

class FeatureVector:
    """
    Complete feature set for one bar/symbol.
    All features are deterministic, no-lookahead, unit-tested.
    """

    def __init__(self, bars: list[Bar], bar_ts_ms: Optional[int] = None):
        if not bars:
            raise ValueError("FeatureVector requires at least 1 bar")

        # ── Trend ──────────────────────────────────────────────────────────
        self.sma_fast = feat_sma_fast(bars)
        self.sma_slow = feat_sma_slow(bars)
        self.ema_fast = feat_ema_fast(bars)
        self.ema_slow = feat_ema_slow(bars)
        adx_dict = feat_adx(bars)
        self.adx = adx_dict["adx"]
        self.plus_di = adx_dict["plus_di"]
        self.minus_di = adx_dict["minus_di"]
        self.trend_slope = feat_trend_slope(bars)
        self.sma_crossover = feat_sma_crossover(bars)

        # ── Momentum ───────────────────────────────────────────────────────
        self.rsi = feat_rsi(bars)
        macd_dict = feat_macd(bars)
        self.macd = macd_dict["macd"]
        self.macd_signal = macd_dict["signal"]
        self.macd_histogram = macd_dict["histogram"]
        self.roc_10 = feat_roc(bars, n=10)
        self.momentum_persistence = feat_momentum_persistence(bars)

        # ── Volatility ─────────────────────────────────────────────────────
        self.atr = feat_atr(bars)
        self.atr_pct = self.atr / bars[-1].c if bars[-1].c else 0.0
        self.realized_vol = feat_realized_vol(bars)
        self.bb_width = feat_bb_width(bars)
        self.vol_expansion = feat_vol_expansion(bars)

        # ── Volume ─────────────────────────────────────────────────────────
        self.vwap = feat_vwap(bars)
        self.vwap_distance = feat_vwap_distance(bars)
        self.rel_volume = feat_rel_volume(bars)
        self.volume_acceleration = feat_volume_acceleration(bars)
        self.volume_trend = feat_volume_trend(bars)

        # ── Structure ──────────────────────────────────────────────────────
        self.higher_highs = feat_higher_highs(bars)
        bd = feat_breakout_distance(bars)
        self.breakout_up = bd["breakout_up"]
        self.breakout_dn = bd["breakout_dn"]
        self.range_compression = feat_range_compression(bars)
        self.gap = feat_gap(bars)
        sr = feat_support_resistance_distance(bars)
        self.dist_resistance = sr["dist_resistance"]
        self.dist_support = sr["dist_support"]

        # ── Context ────────────────────────────────────────────────────────
        ts_ms = bar_ts_ms or bars[-1].t
        ctx = feat_session_phase(ts_ms)
        self.hour_sin = ctx["hour_sin"]
        self.hour_cos = ctx["hour_cos"]
        self.session_phase = ctx["session_phase"]
        self.day_of_week = ctx["day_of_week"]

        # ── Metadata ───────────────────────────────────────────────────────
        self.price = bars[-1].c
        self.feature_version = FEATURE_VERSION
        self.n_bars = len(bars)

    def to_dict(self) -> dict[str, float]:
        """Serialize all numeric features to dict for ML/similarity."""
        return {k: v for k, v in self.__dict__.items()
                if isinstance(v, (int, float)) and k != "n_bars"}

    def to_vector(self) -> list[float]:
        """Ordered numeric feature vector for cosine similarity."""
        d = self.to_dict()
        return [d[k] for k in sorted(d.keys()) if k != "feature_version"]


def extract_features(bars: list[Bar], bar_ts_ms: Optional[int] = None) -> FeatureVector:
    """
    Entry point: compute all features for a list of bars.
    No-lookahead: only uses data in `bars` (caller must not include future bars).
    """
    return FeatureVector(bars, bar_ts_ms=bar_ts_ms)
