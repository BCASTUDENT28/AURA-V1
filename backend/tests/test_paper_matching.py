"""
backend/tests/test_paper_matching.py

Tests for Server-Side Paper Matching Engine.
Verifies:
- Limit buy orders match when limitPrice >= quote.ask or quote.ltp
- Limit sell orders match when limitPrice <= quote.bid or quote.ltp
- Stop-loss and Take-profit trigger detection
- Costs deducted properly per fill
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.paper.matching import PaperMatchingEngine
from backend.app.schemas.types import PaperOrder, PaperPosition, Quote


def test_paper_limit_buy_match():
    """Limit buy executes when limit price is >= current ask."""
    order = PaperOrder(
        id="ord-1",
        ts=1000,
        symbol="NIFTY",
        side="BUY",
        type="LIMIT",
        qty=50,
        limitPrice=24100.0,
        status="OPEN",
    )
    quote = Quote(symbol="NIFTY", ltp=24050.0, bid=24045.0, ask=24055.0)

    fill = PaperMatchingEngine.match_limit_order(order, quote)

    assert fill is not None
    assert fill.price == 24055.0  # filled at ask
    assert fill.qty == 50
    assert order.status == "FILLED"
    assert fill.costs.total > 0


def test_paper_limit_sell_match():
    """Limit sell executes when limit price is <= current bid."""
    order = PaperOrder(
        id="ord-2",
        ts=1000,
        symbol="BANKNIFTY",
        side="SELL",
        type="LIMIT",
        qty=25,
        limitPrice=51000.0,
        status="OPEN",
    )
    quote = Quote(symbol="BANKNIFTY", ltp=51050.0, bid=51040.0, ask=51060.0)

    fill = PaperMatchingEngine.match_limit_order(order, quote)

    assert fill is not None
    assert fill.price == 51040.0  # filled at bid
    assert fill.qty == 25
    assert order.status == "FILLED"
    assert fill.costs.total > 0


def test_paper_limit_unfilled():
    """Limit buy below ask stays OPEN."""
    order = PaperOrder(
        id="ord-3",
        ts=1000,
        symbol="RELIANCE",
        side="BUY",
        type="LIMIT",
        qty=10,
        limitPrice=2800.0,
        status="OPEN",
    )
    quote = Quote(symbol="RELIANCE", ltp=2850.0, bid=2848.0, ask=2852.0)

    fill = PaperMatchingEngine.match_limit_order(order, quote)

    assert fill is None
    assert order.status == "OPEN"


def test_position_stop_loss_trigger():
    """Long position triggers stop loss when LTP drops below stop."""
    pos = PaperPosition(
        symbol="RELIANCE",
        side="BUY",
        qty=10,
        avgPrice=2900.0,
        stop=2850.0,
        target=3000.0,
    )
    quote = Quote(symbol="RELIANCE", ltp=2840.0)

    res = PaperMatchingEngine.check_position_stops(pos, quote)
    assert res is not None
    reason, price = res
    assert reason == "STOP_LOSS"
    assert price == 2850.0
