"""
backend/app/api/routes/quant.py

FastAPI routes for Phase 3 Quant Engine:
- POST /api/quant/features
- POST /api/quant/regime
- GET  /api/quant/strategies
- POST /api/quant/evaluate
"""

from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.data.store import get_market_store
from backend.app.quant.base_strategy import (
    StrategySignal,
    get_strategy,
    list_quant_strategies,
)
from backend.app.quant.features import FeatureVector, extract_features
from backend.app.quant.regime_engine import QuantRegimeEngine, RegimeEvaluation

router = APIRouter(prefix="/api/quant", tags=["Quant Engine & Features"])


class StrategyEvalRequest(BaseModel):
    symbol: str
    strategyId: str
    timeframe: str = "1D"
    params: Optional[dict[str, Any]] = None


class RegimeEvalRequest(BaseModel):
    symbol: str
    timeframe: str = "1D"


@router.get("/strategies")
def get_strategies():
    """List all registered quantitative strategies with parameter schemas and regime suitability."""
    return list_quant_strategies()


@router.post("/features", response_model=FeatureVector)
def get_features_for_symbol(
    symbol: str = Query(..., description="Canonical instrument symbol (e.g. NIFTY, RELIANCE)"),
    timeframe: str = Query("1D", description="Candle timeframe: 1D, 5m, 1m"),
):
    """Compute and extract the full causal Quant Feature Pack for an instrument."""
    store = get_market_store()
    try:
        bars = store.get_bars(symbol, timeframe=timeframe, limit=200, adjusted=True)
        return extract_features(bars)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/regime", response_model=RegimeEvaluation)
def evaluate_market_regime(req: RegimeEvalRequest):
    """Classify the multi-factor market regime for an instrument."""
    store = get_market_store()
    try:
        bars = store.get_bars(req.symbol, timeframe=req.timeframe, limit=200, adjusted=True)
        return QuantRegimeEngine.evaluate_bars(bars)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/evaluate", response_model=StrategySignal)
def evaluate_strategy(req: StrategyEvalRequest):
    """Evaluate a specific quantitative strategy against an instrument."""
    store = get_market_store()
    try:
        bars = store.get_bars(req.symbol, timeframe=req.timeframe, limit=200, adjusted=True)
        strategy = get_strategy(req.strategyId, params=req.params)
        features = extract_features(bars)
        signal = strategy.evaluate(bars, features=features)
        regime = QuantRegimeEngine.classify(features)
        signal.regimeFit = strategy.get_regime_fit(regime.label)
        return signal
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
