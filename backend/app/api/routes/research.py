"""
backend/app/api/routes/research.py

FastAPI routes for Phase 4: Backtesting & Research Laboratory:
- POST /api/research/backtest
- POST /api/research/walk-forward
- GET  /api/research/runs
- GET  /api/research/runs/{run_id}
"""

from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.data.store import get_market_store
from backend.app.quant.base_strategy import get_strategy
from backend.app.research.backtester import BacktestResult, CausalBacktester
from backend.app.research.walk_forward import WalkForwardOptimizer, WalkForwardResult

router = APIRouter(prefix="/api/research", tags=["Backtesting & Research Lab"])

# In-memory registry for backtest run persistence
_RUNS_CACHE: dict[str, BacktestResult] = {}


class BacktestRequest(BaseModel):
    strategyId: str
    symbol: str
    timeframe: str = "1D"
    initialCapital: float = 1_000_000.0
    maxPositionPct: float = 0.10
    params: Optional[dict[str, Any]] = None
    limitBars: int = 500


class WalkForwardRequest(BaseModel):
    strategyId: str
    symbol: str
    paramGrid: list[dict[str, Any]] = Field(default_factory=list)
    trainBars: int = 150
    testBars: int = 40
    stepBars: int = 40


@router.post("/backtest", response_model=BacktestResult)
def run_backtest(req: BacktestRequest):
    """
    Execute a causal, event-driven backtest for a strategy on historical candles:
    - Orders fill at next-bar open or limit match (zero lookahead).
    - Deducts Indian discount-broker transaction costs (STT, Stamp, Exch, SEBI, GST, ₹20 Cap).
    - Generates equity curve and risk-adjusted metrics (Sharpe, Sortino, Drawdown).
    """
    store = get_market_store()
    try:
        bars = store.get_bars(req.symbol, timeframe=req.timeframe, limit=req.limitBars, adjusted=True)
        strat = get_strategy(req.strategyId, params=req.params)
        bt = CausalBacktester(
            strategy=strat,
            initial_capital=req.initialCapital,
            max_position_pct=req.maxPositionPct,
        )
        result = bt.run(req.symbol, bars, timeframe=req.timeframe)
        _RUNS_CACHE[result.runId] = result
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/walk-forward", response_model=WalkForwardResult)
def run_walk_forward_optimization(req: WalkForwardRequest):
    """
    Execute rolling Walk-Forward Optimization (WFO) over In-Sample and Out-of-Sample slices:
    - Optimizes parameters on train windows.
    - Validates strictly on unseen out-of-sample test windows.
    - Prevents curve-fitting and over-optimization bias.
    """
    store = get_market_store()
    try:
        bars = store.get_bars(req.symbol, timeframe="1D", limit=500, adjusted=True)
        optimizer = WalkForwardOptimizer(
            strategy_id=req.strategyId,
            param_grid=req.paramGrid,
            train_bars=req.trainBars,
            test_bars=req.testBars,
            step_bars=req.stepBars,
        )
        return optimizer.run(req.symbol, bars)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs", response_model=list[dict[str, Any]])
def list_backtest_runs():
    """List recent persistent backtest experiment runs and high-level summary metrics."""
    out = []
    for r in _RUNS_CACHE.values():
        out.append({
            "runId": r.runId,
            "strategyId": r.strategyId,
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "netPnl": r.metrics.netPnl,
            "netPnlPct": r.metrics.netPnlPct,
            "sharpeRatio": r.metrics.sharpeRatio,
            "winRate": r.metrics.winRate,
            "maxDrawdownPct": r.metrics.maxDrawdownPct,
            "totalTrades": r.metrics.totalTrades,
        })
    return out


@router.get("/runs/{run_id}", response_model=BacktestResult)
def get_backtest_run_details(run_id: str):
    """Retrieve detailed trade execution log and equity curve for a backtest run."""
    run = _RUNS_CACHE.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Backtest run '{run_id}' not found.")
    return run
