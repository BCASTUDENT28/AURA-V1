"""
backend/app/api/routes/paper.py

FastAPI routes for Phase 5 Paper Trading & Persistent Portfolio State:
- GET  /api/paper/book
- POST /api/paper/order
- POST /api/paper/cancel
- POST /api/paper/reset
- POST /api/paper/match-tick
- GET  /api/paper/session
"""

from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.paper.book import get_paper_store
from backend.app.paper.session import PaperSessionInfo, get_paper_session_manager
from backend.app.schemas.types import (
    OrderSide,
    PaperBook,
    PaperFill,
    RiskSnapshot,
)

router = APIRouter(prefix="/api/paper", tags=["Paper Trading Engine"])


class PaperOrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    qty: int
    limitPrice: float
    stop: Optional[float] = None
    target: Optional[float] = None
    strategyId: Optional[str] = None


class CancelOrderRequest(BaseModel):
    orderId: str


@router.get("/book", response_model=PaperBook)
def get_paper_book():
    """Retrieve the current persistent portfolio book (cash, positions, orders, P&L)."""
    store = get_paper_store()
    return store.get_state()


@router.get("/risk", response_model=RiskSnapshot)
def get_paper_risk():
    """Retrieve the current real-time risk snapshot evaluated over the paper book."""
    store = get_paper_store()
    return store.get_risk_snapshot()


@router.post("/order")
def place_paper_order(req: PaperOrderRequest):
    """
    Place a paper order:
    - Validates against authoritative server-side Risk Engine.
    - If valid, attempts immediate fill against real-time quote.
    - If limit does not cross, queues as OPEN order.
    """
    store = get_paper_store()
    res = store.place_order(
        symbol=req.symbol,
        side=req.side,
        qty=req.qty,
        limit_price=req.limitPrice,
        stop=req.stop,
        target=req.target,
        strategy_id=req.strategyId,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


@router.post("/cancel")
def cancel_paper_order(req: CancelOrderRequest):
    """Cancel an active open limit order."""
    store = get_paper_store()
    success = store.cancel_order(req.orderId)
    if not success:
        raise HTTPException(status_code=404, detail=f"Open order '{req.orderId}' not found.")
    return {"ok": True, "message": f"Order {req.orderId} cancelled."}


@router.post("/reset")
def reset_paper_account():
    """Archive current paper trading session and reset balance to starting capital (₹1,000,000)."""
    store = get_paper_store()
    session_mgr = get_paper_session_manager()

    store.reset_account()
    new_session = session_mgr.archive_and_new_session()
    return {
        "ok": True,
        "message": "Paper trading account reset to ₹1,000,000.",
        "sessionId": new_session.id,
    }


@router.post("/match-tick", response_model=list[PaperFill])
def match_market_tick():
    """Trigger tick matching across open orders and position stop-loss / take-profit brackets."""
    store = get_paper_store()
    new_fills = store.process_market_tick()
    return new_fills


@router.get("/session", response_model=PaperSessionInfo)
def get_session_info():
    """Retrieve metadata about the active paper trading session."""
    session_mgr = get_paper_session_manager()
    return session_mgr.get_current_session()
