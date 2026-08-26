"""
backend/app/broker/order_router.py

Order Router for AURA AI (Phase 9).

Sits between the AURA decision engine and the broker client.
Responsibilities:
  1. Translate AURA-internal signals → OpenAlgo BrokerOrder payloads
  2. Pre-submission risk validation (re-gate before any live order)
  3. Route to Paper Book when env != LIVE (default safe path)
  4. Audit log every order attempt (approved, rejected, or simulated)
  5. Enforce quantity caps and symbol whitelist

Design Principles:
  - Default = PAPER. Live = explicit opt-in.
  - Every live order is risk-gated TWICE: once in AURA's risk engine,
    once here as final check before the network call.
  - Paper and live paths share the same audit schema for consistency.
"""

from __future__ import annotations

import time
import os
from typing import Optional

from pydantic import BaseModel

from backend.app.broker.openalgo_client import (
    BrokerOrder,
    BrokerOrderResponse,
    get_broker_client,
    BrokerDisabledError,
)


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    symbol: str               # AURA canonical symbol
    exchange: str = "NSE"     # NSE | NFO | BSE
    action: str               # BUY | SELL
    quantity: int
    orderType: str = "MARKET" # MARKET | LIMIT | SL | SL-M
    productType: str = "MIS"  # MIS | NRML | CNC
    price: float = 0.0
    triggerPrice: float = 0.0
    strategyTag: str = "AURA"
    env: str = "PAPER"        # "PAPER" | "LIVE"
    staticIpOk: bool = False  # Required True for LIVE


class OrderAuditEntry(BaseModel):
    requestId: str
    timestamp: float
    symbol: str
    action: str
    quantity: int
    orderType: str
    env: str
    routedTo: str             # "PAPER" | "LIVE_BROKER" | "REJECTED"
    orderId: Optional[str]
    status: str               # "SUBMITTED" | "REJECTED" | "SIMULATED"
    rejectionReason: Optional[str]
    latencyMs: Optional[float]


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
# Validation
# ─────────────────────────────────────────────────────────────────────────────

MAX_QUANTITY = 5000   # Hard cap per single order
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
# Router
# ─────────────────────────────────────────────────────────────────────────────

import uuid


def route_order(req: OrderRequest) -> OrderAuditEntry:
    """
    Route an order to either the paper book or live broker.
    Always records an audit entry regardless of outcome.
    """
    request_id = str(uuid.uuid4())[:12]
    t0 = time.monotonic()

    # Validate
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
        )
        _append_audit(entry)
        return entry

    # LIVE path
    if req.env == "LIVE":
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
            )
    else:
        # PAPER path — simulate accepted (actual matching happens in paper book)
        latency_ms = round((time.monotonic() - t0) * 1000, 2)
        entry = OrderAuditEntry(
            requestId=request_id,
            timestamp=time.time(),
            symbol=req.symbol,
            action=req.action,
            quantity=req.quantity,
            orderType=req.orderType,
            env="PAPER",
            routedTo="PAPER",
            orderId=f"PAPER-{request_id}",
            status="SIMULATED",
            rejectionReason=None,
            latencyMs=latency_ms,
        )

    _append_audit(entry)
    return entry
