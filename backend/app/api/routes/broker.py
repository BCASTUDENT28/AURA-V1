"""
backend/app/api/routes/broker.py

Phase 9 Broker Integration API:
  GET  /api/broker/status          – broker connection status
  POST /api/broker/ping            – ping OpenAlgo gateway
  POST /api/broker/order           – route an order (paper or live)
  GET  /api/broker/audit           – order audit log
  GET  /api/broker/positions       – live positions (LIVE mode only)
  GET  /api/broker/funds           – live funds (LIVE mode only)
  POST /api/broker/cancel/{id}     – cancel a live order
  GET  /api/broker/config          – show current broker config (no secrets)
"""

from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException

from backend.app.broker.openalgo_client import (
    get_broker_client,
    BrokerStatus,
    BrokerPosition,
    BrokerFundsResponse,
    BrokerDisabledError,
    BrokerAuthError,
    BrokerOrderError,
)
from backend.app.broker.order_router import (
    OrderRequest,
    OrderAuditEntry,
    route_order,
    get_audit_log,
)

router = APIRouter(prefix="/api/broker", tags=["Broker Integration (Phase 9)"])


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/status", response_model=BrokerStatus)
def broker_status():
    """
    Return current broker connection status.
    Shows whether live trading is enabled, API key is configured, and last latency.
    Does NOT require live-mode — safe to call at any time.
    """
    return get_broker_client().status()


@router.post("/ping")
def ping_broker():
    """
    Ping the OpenAlgo gateway and return latency.
    Requires a running OpenAlgo instance at OPENALGO_BASE_URL.
    """
    try:
        latency_ms = get_broker_client().ping()
        return {"ok": True, "latencyMs": latency_ms,
                "baseUrl": os.environ.get("OPENALGO_BASE_URL", "http://127.0.0.1:5000")}
    except Exception as e:
        raise HTTPException(status_code=503,
                            detail=f"OpenAlgo gateway unreachable: {e}")


@router.post("/order", response_model=OrderAuditEntry)
def submit_order(req: OrderRequest):
    """
    Route an order to paper book (default) or live broker.
    Live orders require: env='LIVE', staticIpOk=True, AURA_LIVE_TRADING=1, OPENALGO_API_KEY set.
    Always returns an audit entry with full traceability.
    """
    return route_order(req)


@router.get("/audit", response_model=list[OrderAuditEntry])
def get_order_audit(limit: int = 100):
    """
    Retrieve the in-memory order audit log.
    Returns most recent entries first.
    """
    log = get_audit_log()
    return list(reversed(log))[:min(limit, 500)]


@router.get("/positions", response_model=list[BrokerPosition])
def get_live_positions():
    """
    Fetch real positions from the broker.
    Requires AURA_LIVE_TRADING=1 and OPENALGO_API_KEY.
    """
    try:
        return get_broker_client().get_positions()
    except BrokerDisabledError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except BrokerAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503,
                            detail=f"Failed to fetch positions: {e}")


@router.get("/funds", response_model=BrokerFundsResponse)
def get_live_funds():
    """
    Fetch available funds from the broker.
    Requires AURA_LIVE_TRADING=1 and OPENALGO_API_KEY.
    """
    try:
        return get_broker_client().get_funds()
    except BrokerDisabledError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except BrokerAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503,
                            detail=f"Failed to fetch funds: {e}")


@router.post("/cancel/{order_id}")
def cancel_live_order(order_id: str):
    """
    Cancel a pending live order by order ID.
    Requires AURA_LIVE_TRADING=1.
    """
    try:
        result = get_broker_client().cancel_order(order_id)
        return {"ok": True, "orderId": order_id, "brokerResponse": result}
    except BrokerDisabledError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except BrokerOrderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Cancel failed: {e}")


@router.get("/config")
def broker_config():
    """
    Show current broker configuration — no secrets exposed.
    Useful for verifying setup without leaking credentials.
    """
    live_enabled = os.environ.get("AURA_LIVE_TRADING", "0") == "1"
    api_key_set = bool(os.environ.get("OPENALGO_API_KEY"))
    base_url = os.environ.get("OPENALGO_BASE_URL", "http://127.0.0.1:5000")
    return {
        "liveEnabled": live_enabled,
        "apiKeyConfigured": api_key_set,
        "baseUrl": base_url,
        "maxQuantityPerOrder": 5000,
        "supportedExchanges": ["NSE", "NFO", "BSE", "MCX"],
        "supportedOrderTypes": ["MARKET", "LIMIT", "SL", "SL-M"],
        "supportedProductTypes": ["MIS", "NRML", "CNC"],
        "staticIpRequired": "For env=LIVE orders only",
        "gatewayDocs": "https://docs.openalgo.in/",
    }
