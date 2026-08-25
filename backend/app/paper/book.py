"""
backend/app/paper/book.py

Persistent Portfolio Book & Position Lifecycle Engine for AURA AI.
Manages:
- Cash, Starting NAV, Realized/Unrealized P&L, and Open Positions
- Risk Engine validation on every order placement
- Weighted average price accounting on position sizing
- Order cancellation and session reset
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from backend.app.data.simulator import quotes_now
from backend.app.engines.cost.cost import estimate_costs
from backend.app.engines.risk.risk import DEFAULT_LIMITS, snapshot_risk
from backend.app.paper.matching import PaperMatchingEngine
from backend.app.schemas.types import (
    STARTING_CASH,
    OrderSide,
    PaperBook,
    PaperFill,
    PaperOrder,
    PaperPosition,
    Quote,
    RiskSnapshot,
)


class PaperBookStore:
    """Server-authoritative portfolio book store."""

    def __init__(self, initial_cash: float = STARTING_CASH):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.realized = 0.0
        self.session_start_nav = initial_cash
        self.kill_switch = False
        self.positions: dict[str, PaperPosition] = {}
        self.orders: list[PaperOrder] = []
        self.fills: list[PaperFill] = []
        self.ops_window: list[int] = []
        self.last_tick = int(time.time() * 1000)

    def get_state(self, quotes: Optional[dict[str, Quote]] = None) -> PaperBook:
        quotes = quotes or quotes_now()
        pos_list = list(self.positions.values())

        # Calculate unrealized P&L
        unrealized = 0.0
        for p in pos_list:
            ltp = quotes.get(p.symbol, Quote(symbol=p.symbol, ltp=p.avgPrice)).ltp
            dir_mult = 1.0 if p.side == "BUY" else -1.0
            unrealized += dir_mult * (ltp - p.avgPrice) * p.qty

        nav = self.cash + sum(p.qty * p.avgPrice for p in pos_list if p.side == "BUY") + unrealized
        daily_pnl = self.realized + unrealized

        return PaperBook(
            cash=round(self.cash, 2),
            positions=pos_list,
            orders=self.orders[-50:],  # last 50 orders
            fills=self.fills[-50:],    # last 50 fills
            realized=round(self.realized, 2),
            dailyPnl=round(daily_pnl, 2),
            sessionStartNav=round(self.session_start_nav, 2),
            killSwitch=self.kill_switch,
        )

    def get_risk_snapshot(self, quotes: Optional[dict[str, Quote]] = None) -> RiskSnapshot:
        quotes = quotes or quotes_now()
        now_ms = int(time.time() * 1000)
        book = self.get_state(quotes)

        return snapshot_risk(
            kill_switch=self.kill_switch,
            book=book,
            quotes=quotes,
            now=now_ms,
            last_tick=self.last_tick,
            ops_window=self.ops_window,
            static_ip_ok=False,  # Paper mode does not require static IP
            env="PAPER",
        )

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        qty: int,
        limit_price: float,
        stop: Optional[float] = None,
        target: Optional[float] = None,
        strategy_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Validate risk and place a paper order.
        Matches immediately if limit crosses, otherwise adds to open order queue.
        """
        now_ms = int(time.time() * 1000)
        quotes = quotes_now()
        quote = quotes.get(symbol, Quote(symbol=symbol, ltp=limit_price))
        self.last_tick = now_ms

        # Record operation for 9 ops/sec throttle
        self.ops_window.append(now_ms)
        self.ops_window = [t for t in self.ops_window if now_ms - t < 1000]

        # 1. Server-Side Risk Gating
        risk_snap = self.get_risk_snapshot(quotes)
        if not risk_snap.canTrade:
            reasons = "; ".join(risk_snap.breaches)
            return {"ok": False, "message": f"Rejected by Risk Engine: {reasons}"}

        if stop is None and DEFAULT_LIMITS.stopRequired:
            return {"ok": False, "message": "Rejected by Risk Engine: Stop-loss is required on all orders."}

        order_id = f"ord-{uuid.uuid4().hex[:8]}"
        order = PaperOrder(
            id=order_id,
            ts=now_ms,
            symbol=symbol,
            side=side,
            type="LIMIT",
            qty=qty,
            limitPrice=limit_price,
            status="OPEN",
            strategyId=strategy_id,
            stop=stop,
            target=target,
        )

        # 2. Attempt Match
        fill = PaperMatchingEngine.match_limit_order(order, quote)
        if fill:
            self._apply_fill(fill, stop=stop, target=target)
            self.orders.append(order)
            self.fills.append(fill)
            return {
                "ok": True,
                "orderId": order.id,
                "status": "FILLED",
                "fillPrice": fill.price,
                "costs": fill.costs.total,
                "message": f"Paper order {side} {qty} {symbol} filled @ {fill.price:.2f}",
            }
        else:
            self.orders.append(order)
            return {
                "ok": True,
                "orderId": order.id,
                "status": "OPEN",
                "message": f"Paper limit order {side} {qty} {symbol} queued @ {limit_price:.2f}",
            }

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        for o in self.orders:
            if o.id == order_id and o.status == "OPEN":
                o.status = "CANCELLED"
                return True
        return False

    def reset_account(self) -> None:
        """Archive session and reset balance to starting capital."""
        self.cash = self.initial_cash
        self.realized = 0.0
        self.session_start_nav = self.initial_cash
        self.kill_switch = False
        self.positions.clear()
        self.orders.clear()
        self.fills.clear()
        self.ops_window.clear()
        self.last_tick = int(time.time() * 1000)

    def process_market_tick(self, quotes: Optional[dict[str, Quote]] = None) -> list[PaperFill]:
        """
        Process tick updates across all open orders and active position stops.
        Returns a list of newly executed fills.
        """
        quotes = quotes or quotes_now()
        new_fills: list[PaperFill] = []

        # 1. Match Open Limit Orders
        for o in self.orders:
            if o.status == "OPEN" and o.symbol in quotes:
                fill = PaperMatchingEngine.match_limit_order(o, quotes[o.symbol])
                if fill:
                    self._apply_fill(fill, stop=o.stop, target=o.target)
                    self.fills.append(fill)
                    new_fills.append(fill)

        # 2. Check Position Stops & Targets
        for sym, pos in list(self.positions.items()):
            if sym in quotes:
                trigger = PaperMatchingEngine.check_position_stops(pos, quotes[sym])
                if trigger:
                    reason, exit_px = trigger
                    exit_side = "SELL" if pos.side == "BUY" else "BUY"
                    # Exit fill
                    turnover = pos.qty * exit_px
                    costs = estimate_costs(
                        turnover=turnover,
                        side=exit_side,
                        product="INTRADAY",
                        kind="equity",
                    )
                    fill = PaperFill(
                        id=f"fill-{uuid.uuid4().hex[:8]}",
                        orderId=f"bracket-{reason.lower()}",
                        ts=int(time.time() * 1000),
                        symbol=sym,
                        side=exit_side,
                        qty=pos.qty,
                        price=exit_px,
                        costs=costs,
                    )
                    self._apply_fill(fill)
                    self.fills.append(fill)
                    new_fills.append(fill)

        return new_fills

    def _apply_fill(
        self,
        fill: PaperFill,
        stop: Optional[float] = None,
        target: Optional[float] = None,
    ) -> None:
        """Update positions and cash balance on fill."""
        sym = fill.symbol
        side = fill.side
        qty = fill.qty
        px = fill.price
        costs = fill.costs.total

        self.cash -= costs

        if sym not in self.positions:
            # New position opened
            self.positions[sym] = PaperPosition(
                symbol=sym,
                side=side,
                qty=qty,
                avgPrice=px,
                stop=stop,
                target=target,
            )
            if side == "BUY":
                self.cash -= (qty * px)
            else:
                self.cash += (qty * px)
        else:
            curr = self.positions[sym]
            if curr.side == side:
                # Add to existing position (weighted average price)
                new_qty = curr.qty + qty
                new_avg = ((curr.qty * curr.avgPrice) + (qty * px)) / new_qty
                curr.qty = new_qty
                curr.avgPrice = round(new_avg, 2)
                if stop:
                    curr.stop = stop
                if target:
                    curr.target = target
                if side == "BUY":
                    self.cash -= (qty * px)
                else:
                    self.cash += (qty * px)
            else:
                # Closing or reducing position
                close_qty = min(curr.qty, qty)
                dir_mult = 1.0 if curr.side == "BUY" else -1.0
                trade_gross = dir_mult * (px - curr.avgPrice) * close_qty

                self.realized += trade_gross
                if curr.side == "BUY":
                    self.cash += (close_qty * px)
                else:
                    self.cash -= (close_qty * px)

                remaining = curr.qty - close_qty
                if remaining > 0:
                    curr.qty = remaining
                else:
                    del self.positions[sym]


# Global singleton paper book store
_paper_store = PaperBookStore()


def get_paper_store() -> PaperBookStore:
    return _paper_store
