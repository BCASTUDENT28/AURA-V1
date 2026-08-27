"""
backend/app/broker/order_router.py

Order Router for AURA AI (Phase 9).

Sits between AURA decision signals and the execution layer.
Responsibilities:
  1. Static validation — exchange, action, quantity, order type (both paths)
  2. Risk gate — calls snapshot_risk() from engines.risk.risk BEFORE any order
     is routed; rejects if canTrade is False. This enforces:
       - Kill switch
       - Daily loss circuit breaker (2% of STARTING_CASH)
       - Portfolio exposure cap (80% NAV)
       - Max simultaneous positions (5)
       - Stale-data check (>5 s)
       - 9 ops/sec throttle
       - Static-IP check (for env=LIVE only)
  3. Routing:
       - env=PAPER  → routed through the real paper book (paper/book.py)
         via place_paper_order(). This is the SAME matching engine used by
         /api/paper/order — not a fake "SIMULATED" entry.
       - env=LIVE   → routed to the OpenAlgo broker client.
  4. Audit log — every attempt (approved or rejected) is recorded.

Single entry point for paper orders:
  /api/broker/order (env=PAPER) internally calls the same book.py path as
  /api/paper/order. Do NOT add a second paper-trading engine.

LIVE trading is disabled by default:
  - Requires AURA_LIVE_TRADING=1 in the environment.
  - Requires staticIpOk=True on the request.
  - Requires OPENALGO_API_KEY in the environment.
  - AURA_LIVE_TRADING must NEVER be set until explicitly authorised.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Optional

from pydantic import BaseModel

from backend.app.broker.openalgo_client import (
    BrokerOrder,
    BrokerOrderResponse,
    get_broker_client,
    BrokerDisabledError,
)
from backend.app.engines.risk.risk import snapshot_risk, DEFAULT_LIMITS
from backend.app.schemas.types import (
    STARTING_CASH,
    PaperBook,
    PaperPosition,
    Quote,
)


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    symbol: str               # AURA canonical symbol
    exchange: str = "NSE"     # NSE | NFO | BSE | MCX
    action: str               # BUY | SELL
    quantity: int
    orderType: str = "MARKET" # MARKET | LIMIT | SL | SL-M
    productType: str = "MIS"  # MIS | NRML | CNC
    price: float = 0.0
    triggerPrice: float = 0.0
    strategyTag: str = "AURA"
    env: str = "PAPER"        # "PAPER" | "LIVE"
    staticIpOk: bool = False  # Required True for env=LIVE


class OrderAuditEntry(BaseModel):
    requestId: str
    timestamp: float
    symbol: str
    action: str
    quantity: int
    orderType: str
    env: str
    routedTo: str             # "PAPER_BOOK" | "LIVE_BROKER" | "REJECTED"
    orderId: Optional[str]
    status: str               # "SUBMITTED" | "REJECTED" | "PAPER_ACCEPTED"
    rejectionReason: Optional[str]
    latencyMs: Optional[float]
    riskCanTrade: Optional[bool]      # snapshot_risk().canTrade result
    riskBreaches: Optional[list[str]] # breaches from risk snapshot


# ─────────────────────────────────────────────────────────────────────────────
# Audit log (in-memory, bounded)
# ─────────────────────────────────────────────────────────────────────────────

_AUDIT_LOG: list[OrderAuditEntry] = []
MAX_AUDIT_ENTRIES = 2000


def get_audit_log() -> list[OrderAuditEntry]:
    return list(_AUDIT_LOG)


def _append_audit(entry: OrderAuditEntry) -> None:
    _AUDIT_LOG.append(entry)
    if len(_AUDIT_LOG) > MAX_AUDIT_ENTRIES:
        _AUDIT_LOG.pop(0)


# ─────────────────────────────────────────────────────────────────────────────
# Static validation (pre-risk, no network)
# ─────────────────────────────────────────────────────────────────────────────

MAX_QUANTITY = 5000
MIN_QUANTITY = 1
VALID_ACTIONS = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "SL", "SL-M"}
VALID_PRODUCT_TYPES = {"MIS", "NRML", "CNC"}
VALID_EXCHANGES = {"NSE", "NFO", "BSE", "MCX"}


def _validate_order(req: OrderRequest) -> Optional[str]:
    """Return rejection reason string, or None if valid."""
    if req.action.upper() not in VALID_ACTIONS:
        return f"Invalid action '{req.action}'; must be BUY or SELL"
    if req.quantity < MIN_QUANTITY or req.quantity > MAX_QUANTITY:
        return f"Quantity {req.quantity} out of bounds [{MIN_QUANTITY}, {MAX_QUANTITY}]"
    if req.orderType.upper() not in VALID_ORDER_TYPES:
        return f"Invalid orderType '{req.orderType}'"
    if req.productType.upper() not in VALID_PRODUCT_TYPES:
        return f"Invalid productType '{req.productType}'"
    if req.exchange.upper() not in VALID_EXCHANGES:
        return f"Invalid exchange '{req.exchange}'"
    if req.env == "LIVE" and not req.staticIpOk:
        return "staticIpOk must be True for LIVE orders (IP whitelisting required)"
    if req.env == "LIVE" and os.environ.get("AURA_LIVE_TRADING", "0") != "1":
        return "AURA_LIVE_TRADING=1 must be set in environment for LIVE orders"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Risk gate — called for EVERY order, paper or live
# ─────────────────────────────────────────────────────────────────────────────

def _run_risk_gate(req: OrderRequest, ops_window: list[int]) -> tuple[bool, list[str]]:
    """
    Call snapshot_risk() and return (canTrade, breaches).
    Uses the live paper book state so kill switch, daily loss, exposure cap,
    position count, stale-data, and ops-rate are all evaluated.

    For env=PAPER: staticIpOk=False is NOT a breach (no broker attached).
    For env=LIVE:  staticIpOk=False IS a breach → already caught in _validate_order,
                   but snapshot_risk enforces it as a second gate.
    """
    from backend.app.paper.book import get_paper_store
    from backend.app.data.simulator import quotes_now

    store = get_paper_store()
    book_state = store.get_state()
    quotes = quotes_now()
    now_ms = int(time.time() * 1000)
    last_tick = store.last_tick

    snap = snapshot_risk(
        kill_switch=store.kill_switch,
        book=book_state,
        quotes=quotes,
        now=now_ms,
        last_tick=last_tick,
        ops_window=ops_window,
        static_ip_ok=req.staticIpOk,
        env=req.env,
    )
    return snap.canTrade, snap.breaches


# ─────────────────────────────────────────────────────────────────────────────
# Ops-rate window (shared mutable state)
# ─────────────────────────────────────────────────────────────────────────────

_OPS_WINDOW: list[int] = []


def _record_op(now_ms: int) -> None:
    """Record an operation timestamp; trim entries older than 1 second."""
    _OPS_WINDOW.append(now_ms)
    cutoff = now_ms - 1000
    while _OPS_WINDOW and _OPS_WINDOW[0] < cutoff:
        _OPS_WINDOW.pop(0)


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

def route_order(req: OrderRequest) -> OrderAuditEntry:
    """
    Route an order to the paper book or live broker.

    Execution sequence:
      1. Static validation (_validate_order) — field/env/IP checks
      2. Risk gate (snapshot_risk) — kill switch, daily loss, exposure,
         position count, stale data, ops/sec throttle
      3a. env=PAPER → place_paper_order() in book.py (real matching engine)
      3b. env=LIVE  → OpenAlgo broker client (requires AURA_LIVE_TRADING=1)

    An audit entry is written for every attempt regardless of outcome.
    riskCanTrade and riskBreaches are always populated after the risk gate runs.
    """
    request_id = str(uuid.uuid4())[:12]
    t0 = time.monotonic()
    now_ms = int(time.time() * 1000)

    # ── Step 1: Static validation ───────────────────────────────────────────
    rejection = _validate_order(req)
    if rejection:
        entry = OrderAuditEntry(
            requestId=request_id,
            timestamp=time.time(),
            symbol=req.symbol,
            action=req.action,
            quantity=req.quantity,
            orderType=req.orderType,
            env=req.env,
            routedTo="REJECTED",
            orderId=None,
            status="REJECTED",
            rejectionReason=rejection,
            latencyMs=None,
            riskCanTrade=None,
            riskBreaches=None,
        )
        _append_audit(entry)
        return entry

    # ── Step 2: Risk gate ────────────────────────────────────────────────────
    can_trade, breaches = _run_risk_gate(req, list(_OPS_WINDOW))
    if not can_trade:
        entry = OrderAuditEntry(
            requestId=request_id,
            timestamp=time.time(),
            symbol=req.symbol,
            action=req.action,
            quantity=req.quantity,
            orderType=req.orderType,
            env=req.env,
            routedTo="REJECTED",
            orderId=None,
            status="REJECTED",
            rejectionReason=f"Risk gate blocked: {'; '.join(breaches)}",
            latencyMs=round((time.monotonic() - t0) * 1000, 2),
            riskCanTrade=False,
            riskBreaches=breaches,
        )
        _append_audit(entry)
        return entry

    # ── Step 3a: PAPER path — real book.py matching engine ──────────────────
    if req.env == "PAPER":
        from backend.app.paper.book import get_paper_store
        from backend.app.schemas.types import OrderSide
        store = get_paper_store()
        side: OrderSide = "BUY" if req.action.upper() == "BUY" else "SELL"
        # limit_price: use req.price if set, otherwise use current LTP from simulator
        from backend.app.data.simulator import quotes_now as _qnow
        _q = _qnow()
        limit_price = req.price if req.price > 0 else (_q.get(req.symbol).ltp if req.symbol in _q else 0.0)

        result = store.place_order(
            symbol=req.symbol,
            side=side,
            qty=req.quantity,
            limit_price=limit_price,
            stop=None,     # stop not required at this layer; book enforces DEFAULT_LIMITS.stopRequired
            target=None,
            strategy_id=req.strategyTag,
        )
        _record_op(now_ms)
        latency_ms = round((time.monotonic() - t0) * 1000, 2)

        if not result.get("ok", False):
            entry = OrderAuditEntry(
                requestId=request_id,
                timestamp=time.time(),
                symbol=req.symbol,
                action=req.action,
                quantity=req.quantity,
                orderType=req.orderType,
                env="PAPER",
                routedTo="REJECTED",
                orderId=None,
                status="REJECTED",
                rejectionReason=result.get("message", "Paper book rejected order"),
                latencyMs=latency_ms,
                riskCanTrade=False,
                riskBreaches=breaches,
            )
        else:
            entry = OrderAuditEntry(
                requestId=request_id,
                timestamp=time.time(),
                symbol=req.symbol,
                action=req.action,
                quantity=req.quantity,
                orderType=req.orderType,
                env="PAPER",
                routedTo="PAPER_BOOK",
                orderId=result.get("orderId"),
                status="PAPER_ACCEPTED",
                rejectionReason=None,
                latencyMs=latency_ms,
                riskCanTrade=True,
                riskBreaches=breaches,  # empty — risk gate passed
            )
        _append_audit(entry)
        return entry

    # ── Step 3b: LIVE path — OpenAlgo broker ────────────────────────────────
    try:
        broker_order = BrokerOrder(
            symbol=req.symbol,
            exchange=req.exchange.upper(),
            action=req.action.upper(),
            quantity=req.quantity,
            orderType=req.orderType.upper(),
            productType=req.productType.upper(),
            price=req.price,
            triggerPrice=req.triggerPrice,
            strategyTag=req.strategyTag,
        )
        client = get_broker_client()
        resp: BrokerOrderResponse = client.place_order(broker_order)
        _record_op(now_ms)
        latency_ms = round((time.monotonic() - t0) * 1000, 2)
        entry = OrderAuditEntry(
            requestId=request_id,
            timestamp=time.time(),
            symbol=req.symbol,
            action=req.action,
            quantity=req.quantity,
            orderType=req.orderType,
            env="LIVE",
            routedTo="LIVE_BROKER",
            orderId=resp.orderId,
            status="SUBMITTED",
            rejectionReason=None,
            latencyMs=latency_ms,
            riskCanTrade=True,
            riskBreaches=breaches,  # empty list (canTrade was True)
        )
    except (BrokerDisabledError, Exception) as e:
        entry = OrderAuditEntry(
            requestId=request_id,
            timestamp=time.time(),
            symbol=req.symbol,
            action=req.action,
            quantity=req.quantity,
            orderType=req.orderType,
            env="LIVE",
            routedTo="REJECTED",
            orderId=None,
            status="REJECTED",
            rejectionReason=str(e),
            latencyMs=None,
            riskCanTrade=True,  # risk passed; broker rejected
            riskBreaches=breaches,
        )

    _append_audit(entry)
    return entry
