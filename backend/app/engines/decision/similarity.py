"""
backend/app/engines/decision/similarity.py

Port of src/lib/aura/similarity.ts
Heuristic nearest-neighbour matching — ported as-is, no ML added.
"""

from __future__ import annotations

import math

from backend.app.engines.decision.indicators import compute_indicators
from backend.app.schemas.types import Bar, SimilarMatch

_memo: dict[str, SimilarMatch] = {}


def _feat(bars: list[Bar], i: int) -> list[float]:
    w = bars[max(0, i - 30): i + 1]
    ind = compute_indicators(w)
    c = bars[i].c
    p5 = bars[i - 5].c if i >= 5 else c
    p20 = bars[i - 20].c if i >= 20 else c
    return [
        (c - p5) / p5 if p5 else 0.0,
        (c - p20) / p20 if p20 else 0.0,
        (ind.rsi - 50) / 50,
        ind.adx / 40,
        ind.realizedVol,
        math.tanh(ind.volumeZ / 2),
        (c - ind.vwap) / (ind.atr if ind.atr else c * 0.01),
    ]


def _dist(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def similar_setups(bars: list[Bar], horizon: int = 5, cache_key: str = None) -> SimilarMatch:
    if cache_key and cache_key in _memo:
        return _memo[cache_key]

    empty = SimilarMatch(n=0, winRate=0.0, avgReturn=0.0, avgMae=0.0, avgMfe=0.0, avgHoldBars=horizon)

    if len(bars) < 80:
        return empty

    last = len(bars) - 1
    target = _feat(bars, last)
    hits: list[dict] = []
    i = 40
    while i < last - horizon - 1:
        d = _dist(_feat(bars, i), target)
        if d < 0.9:
            hits.append({"i": i, "d": d})
        i += 3

    hits.sort(key=lambda x: x["d"])
    top = hits[:32]

    if not top:
        if cache_key:
            _memo[cache_key] = empty
        return empty

    wins = 0
    ret = 0.0
    mae = 0.0
    mfe = 0.0

    for h in top:
        entry = bars[h["i"]].c
        future = bars[h["i"]: h["i"] + horizon + 1]
        exit_price = future[-1].c
        r = (exit_price - entry) / entry if entry else 0.0
        ret += r
        if r > 0:
            wins += 1
        min_ex = 0.0
        max_ex = 0.0
        for b in future:
            min_ex = min(min_ex, (b.l - entry) / entry if entry else 0.0)
            max_ex = max(max_ex, (b.h - entry) / entry if entry else 0.0)
        mae += min_ex
        mfe += max_ex

    n = len(top)
    match = SimilarMatch(
        n=n,
        winRate=wins / n,
        avgReturn=ret / n,
        avgMae=mae / n,
        avgMfe=mfe / n,
        avgHoldBars=horizon,
    )
    if cache_key:
        _memo[cache_key] = match
    return match
