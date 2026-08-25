"""
backend/tests/test_realtime_tick_ingest.py

Tests for Real-Time Tick Ingestion & Dynamic Bar Construction.
Verifies:
- Outlier spike detection and rejection (>10% sudden jump)
- Dynamic 1-minute OHLCV candle formation and interval roll-over
- Metric accounting for throughput and dropped outliers
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.realtime.tick_ingest import (
    RollingBarBuilder,
    TickIngestionEngine,
    TickPacket,
)


@pytest.mark.asyncio
async def test_outlier_spike_rejection():
    """Tick jumping >10% without gradual price movement must be rejected."""
    engine = TickIngestionEngine()

    # Initial normal tick @ 2500
    res1 = await engine.ingest_tick(TickPacket(symbol="RELIANCE", ltp=2500.0, ts=1000))
    assert res1["accepted"] is True

    # Outlier spike @ 3000 (+20% jump)
    res_spike = await engine.ingest_tick(TickPacket(symbol="RELIANCE", ltp=3000.0, ts=2000))
    assert res_spike["accepted"] is False
    assert "Outlier rejected" in res_spike["reason"]
    assert engine.total_outliers_dropped == 1


@pytest.mark.asyncio
async def test_rolling_bar_builder_aggregation():
    """Ticks within the same 60-second window must accumulate into the active bar."""
    builder = RollingBarBuilder("NIFTY", interval_sec=60)

    # Window 0: 0s to 60s
    t1 = builder.process_tick(TickPacket(symbol="NIFTY", ltp=24000.0, volume=10, ts=1000))
    assert t1 is None
    assert builder.current_bar.o == 24000.0
    assert builder.current_bar.h == 24000.0
    assert builder.current_bar.l == 24000.0
    assert builder.current_bar.c == 24000.0
    assert builder.current_bar.v == 10

    # Tick 2: higher price
    builder.process_tick(TickPacket(symbol="NIFTY", ltp=24050.0, volume=15, ts=15000))
    assert builder.current_bar.h == 24050.0
    assert builder.current_bar.c == 24050.0
    assert builder.current_bar.v == 25

    # Tick 3: lower price
    builder.process_tick(TickPacket(symbol="NIFTY", ltp=23980.0, volume=5, ts=45000))
    assert builder.current_bar.l == 23980.0
    assert builder.current_bar.c == 23980.0
    assert builder.current_bar.v == 30

    # Tick in NEXT minute window (70s -> triggers completion of previous 1m bar)
    completed_bar = builder.process_tick(TickPacket(symbol="NIFTY", ltp=24010.0, volume=20, ts=70000))
    assert completed_bar is not None
    assert completed_bar.o == 24000.0
    assert completed_bar.h == 24050.0
    assert completed_bar.l == 23980.0
    assert completed_bar.c == 23980.0
    assert completed_bar.v == 30

    # New bar has open of 24010
    assert builder.current_bar.o == 24010.0
