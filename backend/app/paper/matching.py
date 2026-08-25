"""
backend/app/paper/matching.py

Server-Side Matching Engine for AURA Paper Trading.
Handles:
- Immediate limit-crossing execution against real-time quotes.
- Stop-Loss & Take-Profit triggers on price updates.
- Deducts authoritative Indian discount-broker costs via cost.py.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from backend.app.engines.cost.cost import estimate_costs
from backend.app.schemas.types import (
    OrderSide,
    PaperFill,
    PaperOrder,
    PaperPosition,
    Quote,
)


class PaperMatchingEngine:
    """Matches orders and position stops against live/synthetic quotes."""

    @staticmethod
    def match_limit_order(
        order: PaperOrder,
        quote: Quote,
    ) -> Optional[PaperFill]:
        """
        Evaluate if a limit order is fillable against the quote.
        Returns a PaperFill if executed, else None.
        """
        if order.status != "OPEN":
            return None

        px = quote.ltp
        ask = quote.ask if quote.ask > 0 else px
        bid = quote.bid if quote.bid > 0 else px

        fill_px: Optional[float] = None

        if order.side == "BUY" and order.limitPrice >= ask:
            fill_px = min(order.limitPrice, ask)
        elif order.side == "SELL" and order.limitPrice <= bid:
            fill_px = max(order.limitPrice, bid)

        if fill_px is None:
            return None

        turnover = order.qty * fill_px
        costs = estimate_costs(
            turnover=turnover,
            side=order.side,
            product="INTRADAY",
            kind="equity",
        )

        order.status = "FILLED"
        order.fillPrice = fill_px
        order.costs = costs

        return PaperFill(
            id=f"fill-{uuid.uuid4().hex[:8]}",
            orderId=order.id,
            ts=int(time.time() * 1000),
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            price=fill_px,
            costs=costs,
        )

    @staticmethod
    def check_position_stops(
        pos: PaperPosition,
        quote: Quote,
    ) -> Optional[tuple[str, float]]:
        """
        Check if an active position has hit its Stop-Loss or Take-Profit.
        Returns (exit_reason, exit_price) if triggered, else None.
        """
        px = quote.ltp
        side = pos.side
        stop = pos.stop
        target = pos.target

        if side == "BUY":
            if stop and px <= stop:
                return ("STOP_LOSS", stop)
            if target and px >= target:
                return ("TAKE_PROFIT", target)
        elif side == "SELL":
            if stop and px >= stop:
                return ("STOP_LOSS", stop)
            if target and px <= target:
                return ("TAKE_PROFIT", target)

        return None
