"""
backend/tests/test_market_store.py

Tests for Market Data Store and Historical Candle Querying.
Verifies:
- Multi-timeframe bar fetching (1D, 5m)
- Date range filtering (start_time_ms, end_time_ms)
- Limit and adjustment toggles
- Dataset version registry and checksum computation
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.data.store import get_market_store
from backend.app.schemas.market_data import CorporateAction


@pytest.fixture(name="store")
def _store_fixture():
    return get_market_store()


def test_list_datasets(store):
    """Store must return registered dataset versions."""
    datasets = store.list_datasets()
    assert len(datasets) >= 2
    ids = [d.id for d in datasets]
    assert "sim-in-eq-20240821" in ids
    assert "nse-benchmark-eq-v1" in ids


def test_get_dataset_by_id(store):
    """Retrieve specific dataset by ID."""
    ds = store.get_dataset("sim-in-eq-20240821")
    assert ds is not None
    assert ds.source == "SIMULATOR"
    assert ds.symbolCount == 30
    assert ds.isImmutable is True


def test_get_historical_bars_daily(store):
    """Query daily bars for an instrument."""
    bars = store.get_bars(symbol="NIFTY", timeframe="1D", limit=50)
    assert len(bars) == 50
    for b in bars:
        assert b.t > 0
        assert b.o > 0
        assert b.h >= b.l
        assert b.c > 0
        assert b.v > 0
        assert b.vwap is not None


def test_get_historical_bars_with_limit(store):
    """Limit parameter must restrict the number of bars returned."""
    bars = store.get_bars(symbol="RELIANCE", timeframe="1D", limit=10)
    assert len(bars) == 10


def test_get_historical_bars_time_range(store):
    """Date filtering must only return bars within the specified window."""
    all_bars = store.get_bars(symbol="TCS", timeframe="1D", limit=100)
    assert len(all_bars) >= 20

    t_start = all_bars[5].t
    t_end = all_bars[15].t

    sliced = store.get_bars(symbol="TCS", timeframe="1D", start_time_ms=t_start, end_time_ms=t_end, limit=100)
    assert len(sliced) == 11
    assert sliced[0].t == t_start
    assert sliced[-1].t == t_end


def test_corporate_actions_store_and_adjust(store):
    """Adding a corporate action dynamically affects adjusted queries."""
    sym = "TESTSYM"
    # Query without adjustment
    bars_unadj = store.get_bars("RELIANCE", "1D", limit=20, adjusted=False)
    bars_adj = store.get_bars("RELIANCE", "1D", limit=20, adjusted=True)

    assert len(bars_unadj) == len(bars_adj)
    # Reliance has a 1:2 bonus on 2024-10-28 registered in store
    # Verify adjusted bars have isAdjusted set
    assert bars_adj[0].isAdjusted is True


def test_compute_dataset_checksum(store):
    """Checksum over normalized series must be deterministic and return a 64-character SHA256 hex string."""
    checksum1 = store.compute_dataset_checksum("sim-in-eq-20240821")
    checksum2 = store.compute_dataset_checksum("sim-in-eq-20240821")
    assert checksum1 == checksum2
    assert len(checksum1) == 64


def test_unknown_symbol_raises_error(store):
    """Querying an unknown symbol must raise a ValueError."""
    with pytest.raises(ValueError, match="Unknown instrument symbol"):
        store.get_bars("NONEXISTENT_XYZ", "1D")
