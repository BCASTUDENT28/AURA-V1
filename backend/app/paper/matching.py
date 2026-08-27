"""
backend/app/paper/matching.py

AURA Paper Trading Matching Engine — V2

Implements correct order-type semantics:
  MARKET  — fills immediately at current ask (BUY) or bid (SELL) + slippage
  LIMIT   — fills only if limit price crosses the quote
  SL      — stop-limit: triggers when price hits trigger, then works as LIMIT
  SL-M    — stop-market: triggers when price hits trigger, then fills at market

Slippage model:
  - Base spread: half of (ask - bid) when available, else tick_size
  - Market impact: proportional to order size vs avgVolume (configurable)
  - Configurable slippage_bps override per order

Partial fills:
  - Enabled when order qty > available_qty (estimated from volume assumptions)
  - Partial fill returns a PaperFill with qty < order.qty and updates order.qty

Order expiry:
  - day_only orders expire at session end (configurable)
  - GTC orders remain open until cancelled

Intrabar stop detection:
  - check_position_stops() tests bar.low (for longs) and bar.high (for shorts)
  - Fills at stop price, not at close — correct OHLC assumption
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from backend.app.engines.cost.cost import estimate_costs
from backend.app.schemas.types import (
    Bar,
    OrderSide,
    PaperFill,
    PaperOrder,
    PaperPosition,
    Quote,
)

# ─────────────────────────────────────────────────────────────────────────────
# Slippage configuration
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_SLIPPAGE_BPS = 5.0          # 5 bps = 0.05% base slippage on MARKET orders
DEFAULT_IMPACT_FACTOR = 0.001       # 0.1% extra per 100% of avgVolume traded
MAX_FILL_PCT_OF_VOLUME = 0.25       # Can fill at most 25% of bar volume in one order
MIN_TICK_SIZE = 0.05                # NSE minimum tick (fallback)


def _spread_slippage(quote: Quote, side: OrderSide) -> float:
    """
    Compute realistic bid/ask slippage.
    If bid/ask are available, use half-spread. Otherwise use DEFAULT_SLIPPAGE_BPS.
    """
    if quote.ask > 0 and quote.bid > 0:
        spread = quote.ask - quote.bid
        return spread / 2.0
    # Fallback: bps-based
    ltp = quote.ltp or 1.0
    return ltp * DEFAULT_SLIPPAGE_BPS / 10_000.0


def _market_impact(qty: int, avg_volume: float, px: float) -> float:
    """
    Estimate market impact cost.
    Impact = impact_factor × (order_value / avg_daily_value)
    """
    if avg_volume <= 0:
        return 0.0
    order_value = qty * px
    avg_daily_value = avg_volume * px
    participation = order_value / avg_daily_value
    return participation * DEFAULT_IMPACT_FACTOR * px


def _available_qty(quote: Quote, order_qty: int) -> int:
    """
    Estimate available liquidity for partial fill.
    Uses quote.volume if available, else assumes full fill (no partial).
    """
    if quote.volume > 0:
        available = int(quote.volume * MAX_FILL_PCT_OF_VOLUME)
        return min(order_qty, max(1, available))
    return order_qty  # no partial fills if volume unknown


# ─────────────────────────────────────────────────────────────────────────────
# Matching Engine
# ─────────────────────────────────────────────────────────────────────────────

class PaperMatchingEngine:
    """
    Server-side matching engine for AURA paper trading.
    Handles MARKET, LIMIT, SL, SL-M order types with realistic execution.
    """

    @staticmethod
    def match_order(
        order: PaperOrder,
        quote: Quote,
        avg_volume: float = 0.0,
        slippage_bps: Optional[float] = None,
    ) -> Optional[PaperFill]:
        """
        Primary dispatch: route to correct execution based on order.type.

        Returns PaperFill if executed (full or partial), else None.
        Updates order.status, order.fillPrice, order.qty on partial fills.
        """
        if order.status != "OPEN":
            return None

        ot = (order.type or "LIMIT").upper()

        if ot == "MARKET":
            return PaperMatchingEngine._execute_market(order, quote, avg_volume, slippage_bps)
        elif ot == "LIMIT":
            return PaperMatchingEngine._execute_limit(order, quote, avg_volume)
        elif ot == "SL-M":
            return PaperMatchingEngine._execute_sl_market(order, quote, avg_volume, slippage_bps)
        elif ot == "SL":
            return PaperMatchingEngine._execute_sl_limit(order, quote, avg_volume)
        else:
            # Unknown type — reject
            order.status = "REJECTED"
            return None

    # ── MARKET order ─────────────────────────────────────────────────────────

    @staticmethod
    def _execute_market(
        order: PaperOrder,
        quote: Quote,
        avg_volume: float = 0.0,
        slippage_bps: Optional[float] = None,
    ) -> Optional[PaperFill]:
        """
        MARKET order: fills immediately at ask (BUY) or bid (SELL).
        Applies spread slippage + market impact.
        Supports partial fills based on available liquidity.
        """
        px = quote.ltp
        ask = quote.ask if quote.ask > 0 else px
        bid = quote.bid if quote.bid > 0 else px

        if order.side == "BUY":
            base_px = ask
        else:
            base_px = bid

        # Slippage
        if slippage_bps is not None:
            slip = base_px * slippage_bps / 10_000.0
        else:
            slip = _spread_slippage(quote, order.side)

        # Market impact
        impact = _market_impact(order.qty, avg_volume, base_px)

        if order.side == "BUY":
            fill_px = base_px + slip + impact
        else:
            fill_px = base_px - slip - impact

        fill_px = max(fill_px, MIN_TICK_SIZE)

        # Partial fill check
        fill_qty = _available_qty(quote, order.qty)
        partial = fill_qty < order.qty

        return PaperMatchingEngine._make_fill(order, fill_px, fill_qty, partial)

    # ── LIMIT order ──────────────────────────────────────────────────────────

    @staticmethod
    def _execute_limit(
        order: PaperOrder,
        quote: Quote,
        avg_volume: float = 0.0,
    ) -> Optional[PaperFill]:
        """
        LIMIT order: fills only if limit price crosses ask (BUY) or bid (SELL).
        No additional slippage — fills at min(limitPrice, ask) for BUY.
        """
        px = quote.ltp
        ask = quote.ask if quote.ask > 0 else px
        bid = quote.bid if quote.bid > 0 else px

        fill_px: Optional[float] = None

        if order.side == "BUY" and order.limitPrice >= ask:
            fill_px = min(order.limitPrice, ask)
        elif order.side == "SELL" and order.limitPrice <= bid:
            fill_px = max(order.limitPrice, bid)

        if fill_px is None:
            return None  # Not yet fillable

        fill_qty = _available_qty(quote, order.qty)
        partial = fill_qty < order.qty

        return PaperMatchingEngine._make_fill(order, fill_px, fill_qty, partial)

    # ── SL-M (Stop-Market) order ─────────────────────────────────────────────

    @staticmethod
    def _execute_sl_market(
        order: PaperOrder,
        quote: Quote,
        avg_volume: float = 0.0,
        slippage_bps: Optional[float] = None,
    ) -> Optional[PaperFill]:
        """
        SL-M (Stop-Market): triggers when price crosses triggerPrice,
        then executes as MARKET order.
        BUY SL-M: triggers when ask >= triggerPrice
        SELL SL-M: triggers when bid <= triggerPrice
        """
        if order.triggerPrice is None or order.triggerPrice <= 0:
            # No trigger — treat as MARKET
            return PaperMatchingEngine._execute_market(order, quote, avg_volume, slippage_bps)

        px = quote.ltp
        ask = quote.ask if quote.ask > 0 else px
        bid = quote.bid if quote.bid > 0 else px

        triggered = False
        if order.side == "BUY" and ask >= order.triggerPrice:
            triggered = True
        elif order.side == "SELL" and bid <= order.triggerPrice:
            triggered = True

        if not triggered:
            return None

        # Triggered — execute as market
        return PaperMatchingEngine._execute_market(order, quote, avg_volume, slippage_bps)

    # ── SL (Stop-Limit) order ─────────────────────────────────────────────────

    @staticmethod
    def _execute_sl_limit(
        order: PaperOrder,
        quote: Quote,
        avg_volume: float = 0.0,
    ) -> Optional[PaperFill]:
        """
        SL (Stop-Limit): triggers when price crosses triggerPrice,
        then executes as LIMIT at limitPrice.
        BUY SL: triggers when ask >= triggerPrice, then limit at limitPrice
        SELL SL: triggers when bid <= triggerPrice, then limit at limitPrice
        """
        if order.triggerPrice is None or order.triggerPrice <= 0:
            return PaperMatchingEngine._execute_limit(order, quote, avg_volume)

        px = quote.ltp
        ask = quote.ask if quote.ask > 0 else px
        bid = quote.bid if quote.bid > 0 else px

        triggered = False
        if order.side == "BUY" and ask >= order.triggerPrice:
            triggered = True
        elif order.side == "SELL" and bid <= order.triggerPrice:
            triggered = True

        if not triggered:
            return None

        # Triggered — execute as limit
        return PaperMatchingEngine._execute_limit(order, quote, avg_volume)

    # ── Internal fill factory ─────────────────────────────────────────────────

    @staticmethod
    def _make_fill(
        order: PaperOrder,
        fill_px: float,
        fill_qty: int,
        partial: bool,
    ) -> PaperFill:
        """Create a PaperFill and update the order state."""
        turnover = fill_qty * fill_px
        costs = estimate_costs(
            turnover=turnover,
            side=order.side,
            product="INTRADAY",
            kind="equity",
        )

        if partial:
            order.qty -= fill_qty
            # Order remains OPEN for the remainder
        else:
            order.status = "FILLED"
            order.fillPrice = fill_px
            order.costs = costs

        return PaperFill(
            id=f"fill-{uuid.uuid4().hex[:8]}",
            orderId=order.id,
            ts=int(time.time() * 1000),
            symbol=order.symbol,
            side=order.side,
            qty=fill_qty,
            price=round(fill_px, 2),
            costs=costs,
            partial=partial,
        )

    # ── Legacy compatibility (used in existing tests) ─────────────────────────

    @staticmethod
    def match_limit_order(
        order: PaperOrder,
        quote: Quote,
    ) -> Optional[PaperFill]:
        """
        Backward-compatible alias for LIMIT order matching.
        Existing tests call this directly — do not remove.
        """
        return PaperMatchingEngine._execute_limit(order, quote)

    # ── Position stop/target checking (intrabar-correct) ─────────────────────

    @staticmethod
    def check_position_stops(
        pos: PaperPosition,
        quote: Quote,
    ) -> Optional[tuple[str, float]]:
        """
        Check if an active position has hit Stop-Loss or Take-Profit.

        INTRABAR CORRECTION (V2):
          - BUY positions: stop checked against bar.low (not close)
          - SELL positions: stop checked against bar.high (not close)
          Uses quote.ltp as fallback when bar OHLC not available.

        Returns (exit_reason, exit_price) if triggered, else None.
        """
        px = quote.ltp
        # Use bar extremes if embedded in quote (V2 enriched quotes)
        bar_low = getattr(quote, 'low', None) or getattr(quote, 'barLow', None) or px
        bar_high = getattr(quote, 'high', None) or getattr(quote, 'barHigh', None) or px
        side = pos.side
        stop = pos.stop
        target = pos.target

        if side == "BUY":
            # Check stop against intrabar low (gap-through correct)
            if stop and bar_low <= stop:
                return ("STOP_LOSS", stop)
            if target and bar_high >= target:
                return ("TAKE_PROFIT", target)
        elif side == "SELL":
            # Check stop against intrabar high
            if stop and bar_high >= stop:
                return ("STOP_LOSS", stop)
            if target and bar_low <= target:
                return ("TAKE_PROFIT", target)

        return None

    @staticmethod
    def expire_day_orders(orders: list[PaperOrder]) -> list[str]:
        """
        Expire all OPEN orders with expiry='DAY' (called at session end).
        Returns list of expired order IDs.
        """
        expired: list[str] = []
        for o in orders:
            if o.status == "OPEN" and getattr(o, 'timeInForce', 'DAY') == 'DAY':
                o.status = "CANCELLED"
                expired.append(o.id)
        return expired
