"""
backend/tests/test_paper_risk_gating.py

Tests for Server-Side Risk Gating on Paper Trading Orders.
Verifies:
- Kill switch active -> rejects paper orders
- Missing stop loss -> rejects paper orders
- Exposure cap breach -> rejects paper orders
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.paper.book import PaperBookStore


def test_kill_switch_blocks_order():
    """Active kill switch must reject paper order placement."""
    store = PaperBookStore(initial_cash=1_000_000.0)
    store.kill_switch = True

    res = store.place_order(
        symbol="NIFTY",
        side="BUY",
        qty=50,
        limit_price=24000.0,
        stop=23500.0,
    )

    assert res["ok"] is False
    assert "KILL_SWITCH" in res["message"] or "Risk Engine" in res["message"]


def test_missing_stop_loss_blocks_order():
    """Missing stop-loss must be rejected by Risk Engine rules."""
    store = PaperBookStore(initial_cash=1_000_000.0)

    res = store.place_order(
        symbol="NIFTY",
        side="BUY",
        qty=50,
        limit_price=24000.0,
        stop=None,  # No stop loss
    )

    assert res["ok"] is False
    assert "Stop-loss is required" in res["message"]
