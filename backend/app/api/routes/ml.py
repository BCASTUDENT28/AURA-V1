"""
backend/app/api/routes/ml.py

Phase 7 ML API:
  POST /api/ml/regime          – regime probabilities for a symbol
  POST /api/ml/direction       – directional signal for a symbol
  GET  /api/ml/drift           – drift report for all tracked features
  POST /api/ml/drift/push      – push a feature observation
  GET  /api/ml/drift/summary   – status count summary
  GET  /api/ml/calibrators     – list all calibrator states
  POST /api/ml/calibrate/record – record (raw_prob, label) for a calibrator
  POST /api/ml/calibrate/fit   – trigger calibration fit
  POST /api/ml/calibrate/apply – calibrate a raw probability
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.data.store import get_market_store
from backend.app.quant.features import extract_features

from backend.app.ml.regime_model import classify_regime_probabilities, RegimeProbabilities
from backend.app.ml.direction_model import predict_direction, DirectionSignal
from backend.app.ml.drift_monitor import get_drift_monitor, DriftReport
from backend.app.ml.calibration import (
    get_calibrator, list_calibrators, CalibrationState, CalibrationMethod
)

router = APIRouter(prefix="/api/ml", tags=["ML Architecture (Phase 7)"])


# ─── Request / Response Models ────────────────────────────────────────────────


class SymbolRequest(BaseModel):
    symbol: str
    timeframe: str = "1D"


class DriftPushRequest(BaseModel):
    feature: str
    value: float


class CalibrateRecordRequest(BaseModel):
    calibratorName: str
    rawProb: float
    label: int  # 0 or 1


class CalibrateFitRequest(BaseModel):
    calibratorName: str


class CalibrateApplyRequest(BaseModel):
    calibratorName: str
    rawProb: float
    method: CalibrationMethod = "platt"


class MLInsight(BaseModel):
    symbol: str
    timeframe: str
    regime: RegimeProbabilities
    direction: DirectionSignal


# ─── Routes ───────────────────────────────────────────────────────────────────


@router.post("/regime", response_model=RegimeProbabilities)
def get_regime_probabilities(req: SymbolRequest):
    """
    Compute calibrated regime probabilities for the given symbol.
    Returns softmax-calibrated P() for all 8 regimes with evidence log.
    """
    store = get_market_store()
    bars = store.bars_of(req.symbol, req.timeframe)
    if not bars or len(bars) < 21:
        raise HTTPException(status_code=404, detail=f"Insufficient bars for {req.symbol}")
    feat = extract_features(bars)

    # Feed features into drift monitor
    monitor = get_drift_monitor()
    for field, val in feat.model_dump().items():
        if isinstance(val, (int, float)) and field not in ("t",):
            monitor.push(field, float(val))

    return classify_regime_probabilities(feat)


@router.post("/direction", response_model=DirectionSignal)
def get_direction_signal(req: SymbolRequest):
    """
    Predict directional bias (UP/DOWN/FLAT) with calibrated probabilities.
    Returns expected edge in basis points and entropy-based confidence.
    """
    store = get_market_store()
    bars = store.bars_of(req.symbol, req.timeframe)
    if not bars or len(bars) < 21:
        raise HTTPException(status_code=404, detail=f"Insufficient bars for {req.symbol}")
    feat = extract_features(bars)
    return predict_direction(feat)


@router.post("/insight", response_model=MLInsight)
def get_ml_insight(req: SymbolRequest):
    """
    Combined regime + direction insight in a single call.
    """
    store = get_market_store()
    bars = store.bars_of(req.symbol, req.timeframe)
    if not bars or len(bars) < 21:
        raise HTTPException(status_code=404, detail=f"Insufficient bars for {req.symbol}")
    feat = extract_features(bars)

    monitor = get_drift_monitor()
    for field, val in feat.model_dump().items():
        if isinstance(val, (int, float)) and field not in ("t",):
            monitor.push(field, float(val))

    return MLInsight(
        symbol=req.symbol,
        timeframe=req.timeframe,
        regime=classify_regime_probabilities(feat),
        direction=predict_direction(feat),
    )


# ─── Drift Monitor ────────────────────────────────────────────────────────────


@router.get("/drift", response_model=list[DriftReport])
def get_drift_reports():
    """Return drift reports for all features being tracked."""
    return get_drift_monitor().check_all()


@router.post("/drift/push")
def push_drift_observation(req: DriftPushRequest):
    """Push a single feature observation into the drift monitor."""
    get_drift_monitor().push(req.feature, req.value)
    return {"ok": True, "feature": req.feature}


@router.get("/drift/summary")
def get_drift_summary():
    """Return count of features by drift status: OK, WARN, DRIFT, STALE."""
    return get_drift_monitor().summary()


@router.post("/drift/reset/{feature}")
def reset_drift_baseline(feature: str):
    """Reset baseline for a specific feature (use after confirmed regime shift)."""
    get_drift_monitor().reset_baseline(feature)
    return {"ok": True, "feature": feature, "message": "Baseline reset; will re-establish after next window"}


# ─── Calibration ─────────────────────────────────────────────────────────────


@router.get("/calibrators", response_model=list[CalibrationState])
def get_calibrators():
    """List all registered calibrators and their current state."""
    return list_calibrators()


@router.post("/calibrate/record")
def record_calibration_pair(req: CalibrateRecordRequest):
    """Record a (raw_probability, outcome_label) pair for a named calibrator."""
    if req.label not in (0, 1):
        raise HTTPException(status_code=422, detail="label must be 0 or 1")
    cal = get_calibrator(req.calibratorName, req.method)
    cal.record(req.rawProb, req.label)
    return {"ok": True, "calibrator": req.calibratorName, "nFit": len(cal._samples)}  # type: ignore


@router.post("/calibrate/fit")
def fit_calibrator(req: CalibrateFitRequest):
    """Trigger fitting of a named calibrator. Requires ≥ MIN_FIT_SAMPLES recorded pairs."""
    cal = get_calibrator(req.calibratorName)
    success = cal.fit()
    if not success:
        return {
            "ok": False,
            "message": f"Insufficient samples (need {cal.MIN_FIT_SAMPLES})",  # type: ignore
            "nFit": len(cal._samples)  # type: ignore
        }
    return {"ok": True, "calibrator": req.calibratorName, "state": cal.state.model_dump()}


@router.post("/calibrate/apply")
def apply_calibration(req: CalibrateApplyRequest):
    """Apply calibration to a raw probability. Falls back to identity if not yet fitted."""
    cal = get_calibrator(req.calibratorName, req.method)
    calibrated = cal.calibrate(req.rawProb)
    return {
        "calibratorName": req.calibratorName,
        "rawProb": req.rawProb,
        "calibratedProb": calibrated,
        "isReady": cal.state.isReady,
    }
