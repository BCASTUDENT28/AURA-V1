"""
backend/app/api/routes/market_data.py

FastAPI routes for Phase 2:
- GET  /api/instruments
- GET  /api/instruments/{symbol}
- GET  /api/market/bars
- GET  /api/datasets
- GET  /api/datasets/{dataset_id}
- POST /api/datasets/audit
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from backend.app.data.master import get_instrument_master
from backend.app.data.store import get_market_store
from backend.app.schemas.market_data import (
    DataAuditRequest,
    DataQualityReport,
    DatasetVersion,
    HistoricalBarRecord,
    InstrumentRecord,
)

router = APIRouter(prefix="/api", tags=["Market Data & Instruments"])


# ---------------------------------------------------------------------------
# 1. Instrument Master Endpoints
# ---------------------------------------------------------------------------

@router.get("/instruments", response_model=list[InstrumentRecord])
def list_instruments(
    sector: Optional[str] = Query(None, description="Filter by sector (e.g. Energy, IT, Banks)"),
    segment: Optional[str] = Query(None, description="Filter by segment (e.g. EQUITY, INDEX)"),
    active_only: bool = Query(True, description="Only return active instruments"),
):
    """List all canonical instruments in the AURA universe."""
    master = get_instrument_master()
    return master.list_all(sector=sector, segment=segment, active_only=active_only)


@router.get("/instruments/{symbol}", response_model=InstrumentRecord)
def get_instrument_details(symbol: str):
    """Retrieve detailed instrument master metadata and pre-wired broker mappings."""
    master = get_instrument_master()
    inst = master.get_by_symbol(symbol)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instrument symbol '{symbol}' not found.")
    return inst


# ---------------------------------------------------------------------------
# 2. Historical OHLCV Candle Query Endpoint
# ---------------------------------------------------------------------------

@router.get("/market/bars", response_model=list[HistoricalBarRecord])
def get_historical_bars(
    symbol: str = Query(..., description="Canonical instrument symbol (e.g. NIFTY, RELIANCE)"),
    timeframe: str = Query("1D", description="Candle timeframe: 1m, 3m, 5m, 15m, 1D"),
    start_time_ms: Optional[int] = Query(None, description="Start timestamp in ms (inclusive)"),
    end_time_ms: Optional[int] = Query(None, description="End timestamp in ms (inclusive)"),
    limit: int = Query(520, ge=1, le=5000, description="Max number of bars to return"),
    adjusted: bool = Query(True, description="Apply corporate action backward adjustments"),
):
    """Query multi-timeframe historical OHLCV bars with corporate action adjustment."""
    store = get_market_store()
    try:
        bars = store.get_bars(
            symbol=symbol,
            timeframe=timeframe,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            limit=limit,
            adjusted=adjusted,
        )
        return bars
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# 3. Dataset Versions & Lineage
# ---------------------------------------------------------------------------

@router.get("/datasets", response_model=list[DatasetVersion])
def list_dataset_versions():
    """List all immutable dataset versions and lineage metadata."""
    store = get_market_store()
    return store.list_datasets()


@router.get("/datasets/{dataset_id}", response_model=DatasetVersion)
def get_dataset_version(dataset_id: str):
    """Retrieve metadata and checksum for a specific dataset version."""
    store = get_market_store()
    ds = store.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail=f"Dataset version '{dataset_id}' not found.")
    return ds


# ---------------------------------------------------------------------------
# 4. Data Quality Audits
# ---------------------------------------------------------------------------

@router.post("/datasets/audit", response_model=DataQualityReport)
def trigger_data_quality_audit(req: DataAuditRequest):
    """
    Run automated data quality validation on a dataset version:
    - Verifies trading session continuity
    - Detects duplicate candles and outlier spikes
    - Audits corporate action adjustment applications
    """
    store = get_market_store()
    ds = store.get_dataset(req.datasetVersionId)
    if not ds:
        raise HTTPException(status_code=404, detail=f"Dataset version '{req.datasetVersionId}' not found.")

    report = store.run_quality_audit(
        dataset_id=req.datasetVersionId,
        max_outlier_pct=req.maxOutlierMovePct,
    )
    return report


@router.get("/datasets/{dataset_id}/report", response_model=DataQualityReport)
def get_latest_quality_report(dataset_id: str):
    """Fetch the latest data quality validation report for a dataset."""
    store = get_market_store()
    report = store.get_latest_quality_report(dataset_id)
    if not report:
        # Run audit on demand if not yet generated
        report = store.run_quality_audit(dataset_id)
    return report
