"""
backend/app/realtime/tick_ingest.py

Real-Time Tick Ingestion & Dynamic Rolling Bar Aggregator for AURA AI.
Handles:
- Tick validation and outlier spike filtering (>10% sudden jump).
- Multi-timeframe dynamic candle formation (1-minute, 5-minute bars).
- Event dispatch to EventBus and paper trading matching engine.
"""

from __future__ import annotations

import time
from typing import Any, Optional
from pydantic import BaseModel

from backend.app.realtime.event_bus import get_event_bus
from backend.app.schemas.types import Bar, Quote


class TickPacket(BaseModel):
    symbol: str
    ltp: float
    volume: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    ts: int = 0


class RollingBarBuilder:
    """Accumulates incoming ticks into 1-minute and 5-minute OHLCV candles."""

    def __init__(self, symbol: str, interval_sec: int = 60):
        self.symbol = symbol
        self.interval_sec = interval_sec
        self.current_bar: Optional[Bar] = None
        self.bar_start_ts: int = 0
        self.completed_bars: list[Bar] = []

    def process_tick(self, tick: TickPacket) -> Optional[Bar]:
        """
        Process a tick. If current bar interval is complete, returns the completed Bar.
        Otherwise updates active bar and returns None.
        """
        tick_ts = tick.ts or int(time.time() * 1000)
        bar_window_start = (tick_ts // (self.interval_sec * 1000)) * (self.interval_sec * 1000)

        completed: Optional[Bar] = None

        if self.current_bar is None:
            self.bar_start_ts = bar_window_start
            self.current_bar = Bar(
                t=bar_window_start,
                o=tick.ltp,
                h=tick.ltp,
                l=tick.ltp,
                c=tick.ltp,
                v=tick.volume,
            )
        elif bar_window_start > self.bar_start_ts:
            # Previous bar finished
            completed = self.current_bar
            self.completed_bars.append(completed)
            if len(self.completed_bars) > 500:
                self.completed_bars.pop(0)

            # Start new bar
            self.bar_start_ts = bar_window_start
            self.current_bar = Bar(
                t=bar_window_start,
                o=tick.ltp,
                h=tick.ltp,
                l=tick.ltp,
                c=tick.ltp,
                v=tick.volume,
            )
        else:
            # Update existing bar
            cb = self.current_bar
            cb.h = max(cb.h, tick.ltp)
            cb.l = min(cb.l, tick.ltp)
            cb.c = tick.ltp
            cb.v += tick.volume

        return completed


class TickIngestionEngine:
    """Ingests tick streams, validates continuity, and aggregates bars."""

    def __init__(self):
        self.last_quotes: dict[str, Quote] = {}
        self.bar_builders_1m: dict[str, RollingBarBuilder] = {}
        self.bar_builders_5m: dict[str, RollingBarBuilder] = {}
        self.total_ticks_processed = 0
        self.total_outliers_dropped = 0
        self.start_time = time.time()

    async def ingest_tick(self, tick: TickPacket) -> dict[str, Any]:
        """Ingest, validate, and broadcast a market tick."""
        now_ms = tick.ts or int(time.time() * 1000)
        sym = tick.symbol

        # 1. Outlier Spike Filter (>10% jump against previous quote)
        prev_quote = self.last_quotes.get(sym)
        if prev_quote and prev_quote.ltp > 0:
            pct_change = abs(tick.ltp - prev_quote.ltp) / prev_quote.ltp
            if pct_change > 0.10:
                self.total_outliers_dropped += 1
                return {
                    "accepted": False,
                    "reason": f"Outlier rejected: {pct_change:.1%} jump in single tick ({prev_quote.ltp} -> {tick.ltp})",
                }

        self.total_ticks_processed += 1

        # 2. Build / Update Quote
        spread = max(0.05, tick.ltp * 0.00015)
        bid = tick.bid if tick.bid > 0 else tick.ltp - (spread / 2)
        ask = tick.ask if tick.ask > 0 else tick.ltp + (spread / 2)

        prev_c = prev_quote.ltp if prev_quote else tick.ltp
        chg = tick.ltp - prev_c
        chg_pct = chg / prev_c if prev_c > 0 else 0.0

        quote = Quote(
            symbol=sym,
            ltp=tick.ltp,
            bid=round(bid, 2),
            ask=round(ask, 2),
            open=prev_quote.open if prev_quote else tick.ltp,
            high=max(prev_quote.high if prev_quote else tick.ltp, tick.ltp),
            low=min(prev_quote.low if prev_quote else tick.ltp, tick.ltp),
            prevClose=prev_quote.prevClose if prev_quote else tick.ltp,
            change=round(chg, 2),
            changePct=round(chg_pct, 4),
            volume=tick.volume,
            ts=now_ms,
        )
        self.last_quotes[sym] = quote

        # 3. Aggregate 1m & 5m Bars
        if sym not in self.bar_builders_1m:
            self.bar_builders_1m[sym] = RollingBarBuilder(sym, interval_sec=60)
        if sym not in self.bar_builders_5m:
            self.bar_builders_5m[sym] = RollingBarBuilder(sym, interval_sec=300)

        closed_1m = self.bar_builders_1m[sym].process_tick(tick)
        closed_5m = self.bar_builders_5m[sym].process_tick(tick)

        # 4. Broadcast to EventBus
        bus = get_event_bus()
        await bus.publish(f"quotes:{sym}", quote.model_dump())

        if closed_1m:
            await bus.publish(f"bars:{sym}:1m", closed_1m.model_dump())
        if closed_5m:
            await bus.publish(f"bars:{sym}:5m", closed_5m.model_dump())

        return {
            "accepted": True,
            "quote": quote,
            "closedBar1m": closed_1m is not None,
            "closedBar5m": closed_5m is not None,
        }

    def get_metrics(self) -> dict[str, Any]:
        elapsed = max(1.0, time.time() - self.start_time)
        return {
            "totalTicksProcessed": self.total_ticks_processed,
            "totalOutliersDropped": self.total_outliers_dropped,
            "activeSymbols": len(self.last_quotes),
            "ticksPerSec": round(self.total_ticks_processed / elapsed, 2),
        }


# Global singleton ingestion engine
_tick_engine = TickIngestionEngine()


def get_tick_engine() -> TickIngestionEngine:
    return _tick_engine
