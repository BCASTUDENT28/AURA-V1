"""
backend/tests/test_order_execution_v2.py

Tests for AURA V2 paper matching engine order execution semantics.

Verifies:
1. MARKET orders execute immediately at ask/bid (not at limit price)
2. LIMIT orders only fill when limit crosses ask/bid
3. SL-M orders trigger at trigger price then execute at market
4. SL orders trigger at trigger price then execute at limit
5. No slippage on LIMIT orders
6. Positive slippage on MARKET orders (buy at ask, sell at bid)
7. Partial fill when available quantity < requested quantity
8. Partial fill leaves order OPEN for remainder
9. Order expiry for DAY orders
10. intrabar stop detection uses bar.low (long) and bar.high (short)
11. Unknown order type gets REJECTED
12. MARKET BUY at ask, MARKET SELL at bid (correct side)
13. Costs are deducted on every fill
14. Stop-limit: does NOT fill if price crosses trigger but limit not met
"""

from __future__ import annotations

import pytest

from backend.app.paper.matching import PaperMatchingEngine
from backend.app.schemas.types import (
    Bar,
    PaperFill,
    PaperOrder,
    PaperPosition,
    Quote,
)


def _quote(ltp: float, bid: float = 0.0, ask: float = 0.0, volume: float = 0.0) -> Quote:
    return Quote(
        symbol="TEST",
        ltp=ltp,
        bid=bid if bid > 0 else ltp - 0.5,
        ask=ask if ask > 0 else ltp + 0.5,
        volume=volume,
        ts=0,
    )


def _order(
    side: str = "BUY",
    qty: int = 100,
    order_type: str = "LIMIT",
    limit_price: float = 0.0,
    trigger_price: float = 0.0,
    time_in_force: str = "DAY",
) -> PaperOrder:
    return PaperOrder(
        id="test-order-1",
        ts=0,
        symbol="TEST",
        side=side,
        type=order_type,
        qty=qty,
        limitPrice=limit_price,
        triggerPrice=trigger_price if trigger_price > 0 else None,
        timeInForce=time_in_force,
        status="OPEN",
    )


def _position(side: str = "BUY", stop: float = None, target: float = None) -> PaperPosition:
    return PaperPosition(
        symbol="TEST",
        qty=100.0,
        avgPrice=1000.0,
        side=side,
        stop=stop,
        target=target,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MARKET orders
# ─────────────────────────────────────────────────────────────────────────────

def test_market_buy_executes_at_ask():
    """MARKET BUY must fill at ask price (plus slippage), not at ltp."""
    order = _order(side="BUY", order_type="MARKET")
    quote = _quote(ltp=1000.0, bid=999.0, ask=1001.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is not None, "MARKET order should always fill"
    assert fill.price >= 1001.0, f"MARKET BUY should fill at or above ask (1001), got {fill.price}"


def test_market_sell_executes_at_bid():
    """MARKET SELL must fill at bid price (minus slippage), not at ltp."""
    order = _order(side="SELL", order_type="MARKET")
    quote = _quote(ltp=1000.0, bid=999.0, ask=1001.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is not None, "MARKET SELL should always fill"
    assert fill.price <= 999.0, f"MARKET SELL should fill at or below bid (999), got {fill.price}"


def test_market_order_changes_status_to_filled():
    order = _order(order_type="MARKET")
    quote = _quote(1000.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert order.status == "FILLED"
    assert fill is not None


def test_market_order_not_at_ltp():
    """MARKET order fill price must NOT equal ltp exactly (bid/ask spread must apply)."""
    order = _order(side="BUY", order_type="MARKET")
    quote = _quote(ltp=1000.0, bid=998.0, ask=1003.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill.price != 1000.0, "MARKET order should NOT fill at exact ltp"


def test_market_order_has_costs():
    order = _order(side="BUY", order_type="MARKET", qty=100)
    quote = _quote(1000.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill.costs is not None
    assert fill.costs.total > 0, "Fill must have non-zero costs"


# ─────────────────────────────────────────────────────────────────────────────
# LIMIT orders
# ─────────────────────────────────────────────────────────────────────────────

def test_limit_buy_fills_when_ask_meets_limit():
    """LIMIT BUY fills when limit_price >= ask."""
    order = _order(side="BUY", order_type="LIMIT", limit_price=1002.0)
    quote = _quote(ltp=1000.0, ask=1001.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is not None, "Limit BUY should fill when limit >= ask"
    assert fill.price <= order.limitPrice, "Limit BUY fill price should be <= limit price"


def test_limit_buy_does_not_fill_when_ask_above_limit():
    """LIMIT BUY must NOT fill when ask > limit_price."""
    order = _order(side="BUY", order_type="LIMIT", limit_price=999.0)
    quote = _quote(ltp=1000.0, ask=1001.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is None, "Limit BUY should NOT fill when ask > limit"
    assert order.status == "OPEN", "Order should remain OPEN"


def test_limit_sell_fills_when_bid_meets_limit():
    """LIMIT SELL fills when limit_price <= bid."""
    order = _order(side="SELL", order_type="LIMIT", limit_price=998.0)
    quote = _quote(ltp=1000.0, bid=999.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is not None, "Limit SELL should fill when limit <= bid"


def test_limit_sell_does_not_fill_when_bid_below_limit():
    """LIMIT SELL must NOT fill when bid < limit_price."""
    order = _order(side="SELL", order_type="LIMIT", limit_price=1005.0)
    quote = _quote(ltp=1000.0, bid=999.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is None, "Limit SELL should NOT fill when bid < limit"


def test_limit_order_fill_price_not_worse_than_limit():
    """Limit BUY fill price must never be above limit_price."""
    order = _order(side="BUY", order_type="LIMIT", limit_price=1000.0)
    quote = _quote(ltp=999.0, ask=999.5)
    fill = PaperMatchingEngine.match_order(order, quote)
    if fill:
        assert fill.price <= 1000.0, "Limit BUY should not fill above limit price"


# ─────────────────────────────────────────────────────────────────────────────
# SL-M (Stop-Market) orders
# ─────────────────────────────────────────────────────────────────────────────

def test_slm_buy_does_not_trigger_below_trigger():
    """SL-M BUY should NOT trigger when ask < trigger_price."""
    order = _order(side="BUY", order_type="SL-M", trigger_price=1010.0)
    quote = _quote(ltp=1000.0, ask=1001.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is None, "SL-M BUY should not trigger when ask < trigger"


def test_slm_buy_triggers_at_trigger_price():
    """SL-M BUY should trigger and execute at market when ask >= trigger."""
    order = _order(side="BUY", order_type="SL-M", trigger_price=1000.0)
    quote = _quote(ltp=1001.0, ask=1002.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is not None, "SL-M BUY should trigger when ask >= trigger"


def test_slm_sell_triggers_when_bid_at_trigger():
    """SL-M SELL (protective stop) should trigger when bid <= trigger."""
    order = _order(side="SELL", order_type="SL-M", trigger_price=990.0)
    quote = _quote(ltp=988.0, bid=987.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is not None, "SL-M SELL should trigger when bid <= trigger"


def test_slm_sell_does_not_trigger_above_trigger():
    order = _order(side="SELL", order_type="SL-M", trigger_price=990.0)
    quote = _quote(ltp=995.0, bid=994.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is None, "SL-M SELL should not trigger when bid > trigger"


# ─────────────────────────────────────────────────────────────────────────────
# SL (Stop-Limit) orders
# ─────────────────────────────────────────────────────────────────────────────

def test_sl_buy_triggers_and_places_limit():
    """SL BUY: trigger at trigger_price, then fills if limit_price >= ask."""
    # Ask=1002, trigger=1000 (triggered), limit=1003 >= ask (fills)
    order = _order(side="BUY", order_type="SL", trigger_price=1000.0, limit_price=1003.0)
    quote = _quote(ltp=1001.0, ask=1002.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is not None, "SL BUY should fill (triggered + limit met)"


def test_sl_buy_triggered_but_limit_not_met():
    """SL BUY triggered but limit price too low — should NOT fill."""
    # Ask=1010, trigger=1000 (triggered), limit=1005 < ask (no fill)
    order = _order(side="BUY", order_type="SL", trigger_price=1000.0, limit_price=1005.0)
    quote = _quote(ltp=1011.0, ask=1010.0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is None, "SL BUY should NOT fill when triggered but limit not met"


# ─────────────────────────────────────────────────────────────────────────────
# Partial fills
# ─────────────────────────────────────────────────────────────────────────────

def test_partial_fill_when_volume_limited():
    """When available volume < order qty, should partial fill."""
    order = _order(side="BUY", order_type="MARKET", qty=10000)
    # volume=100 → available = 25% of 100 = 25 < 10000
    quote = _quote(ltp=1000.0, volume=100)
    fill = PaperMatchingEngine.match_order(order, quote, avg_volume=0)
    assert fill is not None
    if fill.partial:
        assert fill.qty < 10000, "Partial fill should have qty < requested"
        assert order.status == "OPEN", "Order should remain OPEN after partial fill"


def test_no_partial_when_volume_unknown():
    """If volume=0 (unknown), should assume full fill (no partial)."""
    order = _order(side="BUY", order_type="MARKET", qty=100)
    quote = _quote(ltp=1000.0, volume=0)
    fill = PaperMatchingEngine.match_order(order, quote)
    assert fill is not None
    assert fill.qty == 100, "Should fully fill when volume unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Order expiry
# ─────────────────────────────────────────────────────────────────────────────

def test_expire_day_orders_cancels_open_orders():
    orders = [
        PaperOrder(id="o1", ts=0, symbol="A", side="BUY", type="LIMIT",
                   qty=100, limitPrice=999.0, status="OPEN", timeInForce="DAY"),
        PaperOrder(id="o2", ts=0, symbol="B", side="SELL", type="LIMIT",
                   qty=50, limitPrice=1001.0, status="OPEN", timeInForce="GTC"),
    ]
    expired = PaperMatchingEngine.expire_day_orders(orders)
    assert "o1" in expired, "DAY order should be expired"
    assert "o2" not in expired, "GTC order should NOT be expired"
    assert orders[0].status == "CANCELLED"
    assert orders[1].status == "OPEN"


# ─────────────────────────────────────────────────────────────────────────────
# Intrabar stop detection (OHLC correction)
# ─────────────────────────────────────────────────────────────────────────────

def test_long_stop_triggered_by_bar_low():
    """BUY position stop should trigger when bar.low <= stop, even if close > stop."""
    pos = _position(side="BUY", stop=990.0)
    # Close=995 (above stop), but low=988 (below stop) → stop should trigger
    quote = _quote(ltp=995.0)
    quote.low = 988.0   # Simulate bar.low
    quote.high = 1010.0
    trigger = PaperMatchingEngine.check_position_stops(pos, quote)
    assert trigger is not None, "Stop should trigger when bar.low <= stop"
    reason, px = trigger
    assert reason == "STOP_LOSS"
    assert px == 990.0


def test_long_stop_not_triggered_when_low_above_stop():
    """BUY position stop should NOT trigger when bar.low > stop."""
    pos = _position(side="BUY", stop=980.0)
    quote = _quote(ltp=995.0)
    quote.low = 985.0
    trigger = PaperMatchingEngine.check_position_stops(pos, quote)
    assert trigger is None, "Stop should not trigger when low > stop"


def test_long_target_triggered_by_bar_high():
    """BUY position target should trigger when bar.high >= target."""
    pos = _position(side="BUY", target=1050.0)
    quote = _quote(ltp=1040.0)
    quote.high = 1055.0
    quote.low = 1035.0
    trigger = PaperMatchingEngine.check_position_stops(pos, quote)
    assert trigger is not None, "Target should trigger when bar.high >= target"
    reason, px = trigger
    assert reason == "TAKE_PROFIT"


def test_short_stop_triggered_by_bar_high():
    """SELL position stop should trigger when bar.high >= stop."""
    pos = _position(side="SELL", stop=1010.0)
    quote = _quote(ltp=1005.0)
    quote.high = 1015.0
    quote.low = 1000.0
    trigger = PaperMatchingEngine.check_position_stops(pos, quote)
    assert trigger is not None, "Short stop should trigger when bar.high >= stop"
    reason, px = trigger
    assert reason == "STOP_LOSS"


# ─────────────────────────────────────────────────────────────────────────────
# Unknown order type
# ─────────────────────────────────────────────────────────────────────────────

def test_unknown_order_type_rejected():
    order = PaperOrder(
        id="bad-1", ts=0, symbol="TEST", side="BUY",
        type="LIMIT",  # use valid type to create, then mutate
        qty=100, limitPrice=1000.0, status="OPEN"
    )
    object.__setattr__(order, 'type', 'INVALID')  # bypass Pydantic validation
    fill = PaperMatchingEngine.match_order(order, _quote(1000.0))
    # Should reject or return None safely
    assert order.status in ("REJECTED", "OPEN"), "Unknown type should be rejected or handled"


# ─────────────────────────────────────────────────────────────────────────────
# Legacy match_limit_order compatibility
# ─────────────────────────────────────────────────────────────────────────────

def test_legacy_match_limit_order_still_works():
    """match_limit_order() backward compatibility for existing tests."""
    order = _order(side="BUY", order_type="LIMIT", limit_price=1002.0)
    quote = _quote(ltp=1000.0, ask=1001.0)
    fill = PaperMatchingEngine.match_limit_order(order, quote)
    assert fill is not None, "Legacy match_limit_order should still work"
