"""
backend/app/api/routes/decisions.py

FastAPI routes:
  GET  /api/universe/decisions  → list[Decision]
  GET  /api/risk/snapshot       → RiskSnapshot
  POST /api/paper/order         → { decision_ok, cost, message }

IMPORTANT:
  - POST /api/paper/order does NOT write a risk_events row directly.
    The write happens inside snapshot_risk() as a side effect of evaluating
    the risk — the route only calls snapshot_risk() and rejects if BLOCK-level.
  - No broker calls, no live credentials, no live order paths.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.data.simulator import bars_of, get_universe, seed_quotes, PAPER_OPEN
from backend.app.engines.cost.cost import estimate_costs
from backend.app.engines.decision.decision import compute_decision, decide_universe
from backend.app.engines.risk.risk import snapshot_risk
from backend.app.schemas.types import (
    CostBreakdown,
    Decision,
    Learning,
    PaperBook,
    Quote,
    RiskSnapshot,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /api/universe/decisions
# ---------------------------------------------------------------------------

@router.get("/api/universe/decisions", response_model=list[Decision])
def get_universe_decisions(
    symbols: Optional[str] = Query(None, description="Comma-separated symbol list. Defaults to full universe."),
):
    """
    Compute and return decisions for all (or the requested subset of) symbols.
    Uses the backend simulator to generate quotes — frontend must not compute decisions.
    """
    quotes = seed_quotes(PAPER_OPEN)

    if symbols:
        requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        quotes = {s: q for s, q in quotes.items() if s in requested}

    decisions = decide_universe(quotes, learnings=[])
    return decisions


# ---------------------------------------------------------------------------
# GET /api/risk/snapshot
# ---------------------------------------------------------------------------

class RiskSnapshotRequest(BaseModel):
    kill_switch: bool = False
    cash: float = 1_000_000.0
    positions: list = []   # list[PaperPosition] — passed from client
    daily_pnl: float = 0.0
    now: int
    last_tick: int
    ops_window: list[int] = []


@router.get("/api/risk/snapshot", response_model=RiskSnapshot)
def get_risk_snapshot(
    kill_switch: bool = Query(False),
    now: int = Query(PAPER_OPEN),
    last_tick: int = Query(PAPER_OPEN),
    daily_pnl: float = Query(0.0),
    open_positions: int = Query(0),
    ops_window_len: int = Query(0),
):
    """
    Return a risk snapshot for the current paper book state.
    Uses env="PAPER" and static_ip_ok=False (no broker attached in paper mode).
    """
    quotes = seed_quotes(now)

    # Construct a minimal empty book for the snapshot
    book = PaperBook(
        cash=1_000_000.0 - abs(daily_pnl),
        dailyPnl=daily_pnl,
        positions=[],
    )

    snap = snapshot_risk(
        kill_switch=kill_switch,
        book=book,
        quotes=quotes,
        now=now,
        last_tick=last_tick,
        ops_window=[now] * min(ops_window_len, 20),
        static_ip_ok=False,   # no broker in PAPER — see compliance-check scoping
        env="PAPER",
    )
    return snap


# ---------------------------------------------------------------------------
# POST /api/paper/order
# ---------------------------------------------------------------------------

class PaperOrderRequest(BaseModel):
    symbol: str
    side: str             # "BUY" | "SELL"
    qty: float
    limit_price: float
    stop: Optional[float] = None
    target: Optional[float] = None
    strategy_id: Optional[str] = None
    product: str = "INTRADAY"   # "INTRADAY" | "DELIVERY"
    kind: str = "equity"        # "index" | "equity"
    kill_switch: bool = False
    now: int = PAPER_OPEN
    last_tick: int = PAPER_OPEN
    daily_pnl: float = 0.0
    ops_window: list[int] = []


class PaperOrderResponse(BaseModel):
    ok: bool
    message: str
    cost: Optional[CostBreakdown] = None
    risk: Optional[RiskSnapshot] = None


@router.post("/api/paper/order", response_model=PaperOrderResponse)
def place_paper_order(req: PaperOrderRequest):
    """
    Validate a paper order against the risk engine, then estimate costs.

    The risk_events row (if any) is written INSIDE snapshot_risk() as a
    side effect — this route never writes directly.
    """
    quotes = seed_quotes(req.now)
    book = PaperBook(
        cash=1_000_000.0 - abs(req.daily_pnl),
        dailyPnl=req.daily_pnl,
        positions=[],
    )

    risk = snapshot_risk(
        kill_switch=req.kill_switch,
        book=book,
        quotes=quotes,
        now=req.now,
        last_tick=req.last_tick,
        ops_window=req.ops_window,
        static_ip_ok=False,
        env="PAPER",
    )

    if not risk.canTrade:
        return PaperOrderResponse(
            ok=False,
            message=f"Order rejected by risk engine: {'; '.join(risk.breaches)}",
            risk=risk,
        )

    turnover = req.qty * req.limit_price
    cost = estimate_costs(
        turnover=turnover,
        side=req.side,
        product=req.product,
        kind=req.kind,
    )

    return PaperOrderResponse(
        ok=True,
        message=f"Paper order accepted: {req.side} {req.qty} {req.symbol} @ {req.limit_price:.2f}",
        cost=cost,
        risk=risk,
    )
