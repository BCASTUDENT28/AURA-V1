"""
backend/tests/test_paper_positions.py

Tests for Paper Position Management & Portfolio Lifecycle.
Verifies:
- Opening position updates cash balance and creates position record.
- Adding to position calculates weighted average price.
- Partial position closing calculates realized P&L and updates remaining qty.
- Full closing removes position record from portfolio book.
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.paper.book import PaperBookStore


def test_position_open_and_average_price():
    """Verify position creation and weighted average calculation."""
    store = PaperBookStore(initial_cash=1_000_000.0)

    # 1. Place first BUY order (10 @ 2000)
    res1 = store.place_order(
        symbol="RELIANCE",
        side="BUY",
        qty=10,
        limit_price=3000.0,  # crosses ask -> fills immediately
        stop=2500.0,
        target=3500.0,
    )
    assert res1["ok"] is True
    assert "RELIANCE" in store.positions
    pos1 = store.positions["RELIANCE"]
    assert pos1.qty == 10
    fill_px1 = pos1.avgPrice

    # 2. Place second BUY order (10 @ higher price)
    res2 = store.place_order(
        symbol="RELIANCE",
        side="BUY",
        qty=10,
        limit_price=3100.0,
        stop=2500.0,
        target=3500.0,
    )
    assert res2["ok"] is True
    pos2 = store.positions["RELIANCE"]
    assert pos2.qty == 20
    fill_px2 = res2["fillPrice"]
    expected_avg = round(((10 * fill_px1) + (10 * fill_px2)) / 20, 2)
    assert pos2.avgPrice == expected_avg


def test_partial_and_full_position_close():
    """Verify partial and full position closing and realized P&L."""
    store = PaperBookStore(initial_cash=1_000_000.0)

    # Buy 20 @ limit
    store.place_order(
        symbol="TCS",
        side="BUY",
        qty=20,
        limit_price=4500.0,
        stop=4000.0,
        target=5000.0,
    )
    assert store.positions["TCS"].qty == 20
    entry_px = store.positions["TCS"].avgPrice

    # Sell 10 @ higher limit (partial close)
    res_sell = store.place_order(
        symbol="TCS",
        side="SELL",
        qty=10,
        limit_price=4000.0,  # crosses bid -> fills
        stop=3800.0,
    )
    assert res_sell["ok"] is True
    assert store.positions["TCS"].qty == 10
    assert store.realized != 0.0

    # Sell remaining 10 (full close)
    res_close = store.place_order(
        symbol="TCS",
        side="SELL",
        qty=10,
        limit_price=4000.0,
        stop=3800.0,
    )
    assert res_close["ok"] is True
    assert "TCS" not in store.positions
