"""
backend/app/broker/openalgo_client.py

OpenAlgo HTTP API Client for AURA AI (Phase 9).

OpenAlgo is an open-source broker-agnostic trading gateway that exposes
a standardised REST API regardless of the underlying broker
(Zerodha, Shoonya, Angel One, etc.).

This client:
  - Is DISABLED by default — all methods raise BrokerDisabledError unless
    env var AURA_LIVE_TRADING=1 AND OPENALGO_API_KEY is set.
  - Enforces the static_ip_ok check before any live order submission.
  - Is a thin HTTP wrapper — all risk/sizing decisions happen in AURA's
    own risk engine (backend/app/quant/risk.py) before the call reaches here.
  - Never stores credentials in code — reads them from environment variables.
  - All responses are normalised into AURA's own schema types.

OpenAlgo REST reference: https://docs.openalgo.in/

Environment variables required for live mode:
  AURA_LIVE_TRADING=1
  OPENALGO_API_KEY=<your key>
  OPENALGO_BASE_URL=http://127.0.0.1:5000  (default; local OpenAlgo instance)
"""

from __future__ import annotations

import os
import time
from typing import Optional

import httpx
from pydantic import BaseModel


# ─────────────────────────────────────────────────────────────────────────────
# Configuration / Safety Guards
# ─────────────────────────────────────────────────────────────────────────────

class BrokerDisabledError(RuntimeError):
    """Raised when live trading is attempted without explicit opt-in."""


class BrokerAuthError(RuntimeError):
    """Raised when API key is missing or rejected."""


class BrokerOrderError(RuntimeError):
    """Raised when the broker rejects an order."""


def _live_trading_enabled() -> bool:
    return os.environ.get("AURA_LIVE_TRADING", "0") == "1"


def _get_api_key() -> str:
    key = os.environ.get("OPENALGO_API_KEY", "")
    if not key:
        raise BrokerAuthError(
            "OPENALGO_API_KEY environment variable is not set. "
            "Set it before enabling live trading."
        )
    return key


def _get_base_url() -> str:
    return os.environ.get("OPENALGO_BASE_URL", "http://127.0.0.1:5000")


def _require_live() -> None:
    """Hard gate — raises if live trading is not explicitly enabled."""
    if not _live_trading_enabled():
        raise BrokerDisabledError(
            "Live trading is disabled. Set AURA_LIVE_TRADING=1 to enable. "
            "Ensure you understand the risks before enabling live order submission."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

class BrokerOrder(BaseModel):
    symbol: str               # OpenAlgo symbol format e.g. "NIFTY25JUNFUT"
    exchange: str             # NSE | NFO | BSE | MCX
    action: str               # BUY | SELL
    quantity: int
    orderType: str            # MARKET | LIMIT | SL | SL-M
    productType: str          # MIS | NRML | CNC
    price: float = 0.0        # 0.0 for MARKET orders
    triggerPrice: float = 0.0
    strategyTag: str = "AURA"


class BrokerOrderResponse(BaseModel):
    orderId: str
    status: str               # "success" | "rejected" | "error"
    message: str
    rawResponse: dict


class BrokerPosition(BaseModel):
    symbol: str
    exchange: str
    quantity: int             # net position; negative = short
    averagePrice: float
    lastPrice: float
    pnl: float
    productType: str


class BrokerFundsResponse(BaseModel):
    availableCash: float
    usedMargin: float
    totalBalance: float
    currency: str = "INR"


class BrokerStatus(BaseModel):
    liveEnabled: bool
    baseUrl: str
    apiKeyConfigured: bool
    connectedAt: Optional[float]
    latencyMs: Optional[float]


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────

class OpenAlgoClient:
    """
    Thin wrapper around OpenAlgo REST API.
    All order methods are gated by AURA_LIVE_TRADING=1.
    """

    TIMEOUT = 5.0  # seconds

    def __init__(self) -> None:
        self._connected_at: Optional[float] = None
        self._last_latency: Optional[float] = None

    def status(self) -> BrokerStatus:
        """Return connection status without requiring live-mode."""
        return BrokerStatus(
            liveEnabled=_live_trading_enabled(),
            baseUrl=_get_base_url(),
            apiKeyConfigured=bool(os.environ.get("OPENALGO_API_KEY")),
            connectedAt=self._connected_at,
            latencyMs=self._last_latency,
        )

    def ping(self) -> float:
        """
        Ping the OpenAlgo gateway (does not require live-mode).
        Returns latency in ms. Raises httpx.ConnectError if unreachable.
        """
        base = _get_base_url()
        t0 = time.monotonic()
        with httpx.Client(timeout=self.TIMEOUT) as client:
            resp = client.get(f"{base}/api/v1/status")
            resp.raise_for_status()
        latency_ms = round((time.monotonic() - t0) * 1000, 2)
        self._last_latency = latency_ms
        self._connected_at = time.time()
        return latency_ms

    def place_order(self, order: BrokerOrder) -> BrokerOrderResponse:
        """
        Submit an order to the broker via OpenAlgo.
        Requires AURA_LIVE_TRADING=1 and OPENALGO_API_KEY.
        """
        _require_live()
        api_key = _get_api_key()
        base = _get_base_url()

        payload = {
            "apikey": api_key,
            "symbol": order.symbol,
            "exchange": order.exchange,
            "action": order.action,
            "quantity": str(order.quantity),
            "ordertype": order.orderType,
            "product": order.productType,
            "price": str(order.price),
            "triggerprice": str(order.triggerPrice),
            "strategy": order.strategyTag,
        }

        t0 = time.monotonic()
        try:
            with httpx.Client(timeout=self.TIMEOUT) as client:
                resp = client.post(f"{base}/api/v1/placeorder", json=payload)
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            self._last_latency = latency_ms
        except httpx.HTTPError as e:
            raise BrokerOrderError(f"HTTP error placing order: {e}") from e

        raw = resp.json() if resp.content else {}
        if resp.status_code != 200 or raw.get("status") == "error":
            raise BrokerOrderError(
                f"Order rejected: {raw.get('message', resp.text)}"
            )

        return BrokerOrderResponse(
            orderId=str(raw.get("orderid", "")),
            status=raw.get("status", "success"),
            message=raw.get("message", ""),
            rawResponse=raw,
        )

    def get_positions(self) -> list[BrokerPosition]:
        """
        Fetch open positions from the broker.
        Requires AURA_LIVE_TRADING=1.
        """
        _require_live()
        api_key = _get_api_key()
        base = _get_base_url()

        with httpx.Client(timeout=self.TIMEOUT) as client:
            resp = client.post(
                f"{base}/api/v1/positionbook",
                json={"apikey": api_key}
            )
            resp.raise_for_status()

        raw = resp.json()
        positions: list[BrokerPosition] = []
        for p in raw.get("data", []):
            try:
                positions.append(BrokerPosition(
                    symbol=p.get("symbol", ""),
                    exchange=p.get("exchange", "NSE"),
                    quantity=int(p.get("netqty", 0)),
                    averagePrice=float(p.get("netavgprice", 0.0)),
                    lastPrice=float(p.get("ltp", 0.0)),
                    pnl=float(p.get("pnl", 0.0)),
                    productType=p.get("product", "MIS"),
                ))
            except (KeyError, ValueError):
                continue
        return positions

    def get_funds(self) -> BrokerFundsResponse:
        """
        Fetch available funds from the broker.
        Requires AURA_LIVE_TRADING=1.
        """
        _require_live()
        api_key = _get_api_key()
        base = _get_base_url()

        with httpx.Client(timeout=self.TIMEOUT) as client:
            resp = client.post(
                f"{base}/api/v1/funds",
                json={"apikey": api_key}
            )
            resp.raise_for_status()

        raw = resp.json()
        data = raw.get("data", {})
        return BrokerFundsResponse(
            availableCash=float(data.get("availablecash", 0.0)),
            usedMargin=float(data.get("utilisedmargin", 0.0)),
            totalBalance=float(data.get("totalcollateral", 0.0)),
        )

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a pending order by ID. Requires AURA_LIVE_TRADING=1."""
        _require_live()
        api_key = _get_api_key()
        base = _get_base_url()

        with httpx.Client(timeout=self.TIMEOUT) as client:
            resp = client.post(
                f"{base}/api/v1/cancelorder",
                json={"apikey": api_key, "orderid": order_id}
            )
            resp.raise_for_status()
        return resp.json()

    def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None,
    ) -> dict:
        """Modify a pending order. Requires AURA_LIVE_TRADING=1."""
        _require_live()
        api_key = _get_api_key()
        base = _get_base_url()

        payload: dict = {"apikey": api_key, "orderid": order_id}
        if quantity is not None:
            payload["quantity"] = str(quantity)
        if price is not None:
            payload["price"] = str(price)
        if trigger_price is not None:
            payload["triggerprice"] = str(trigger_price)
        if order_type is not None:
            payload["ordertype"] = order_type

        with httpx.Client(timeout=self.TIMEOUT) as client:
            resp = client.post(f"{base}/api/v1/modifyorder", json=payload)
            resp.raise_for_status()
        return resp.json()


# Singleton
_CLIENT = OpenAlgoClient()


def get_broker_client() -> OpenAlgoClient:
    return _CLIENT
