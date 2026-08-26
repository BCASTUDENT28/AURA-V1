"""
backend/app/main.py

FastAPI application entry point.
Start with: uvicorn backend.app.main:app --reload
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes.broker import router as broker_router
from backend.app.api.routes.decisions import router as decisions_router
from backend.app.api.routes.market_data import router as market_data_router
from backend.app.api.routes.ml import router as ml_router
from backend.app.api.routes.paper import router as paper_router
from backend.app.api.routes.quant import router as quant_router
from backend.app.api.routes.realtime import router as realtime_router
from backend.app.api.routes.research import router as research_router
from backend.app.api.routes.similarity import router as similarity_router

app = FastAPI(
    title="AURA Backend — Phase 9",
    description=(
        "Full quant stack: Market Data · Feature Engine · Backtesting · Paper Trading · "
        "Real-Time Gateway · ML Architecture · Evidence Memory · "
        "OpenAlgo Broker Integration (paper-default, live-gated)."
    ),
    version="9.0.0",
)

# CORS — allow the Vite/TanStack frontend running on localhost
CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000,http://127.0.0.1:8080",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(broker_router)
app.include_router(decisions_router)
app.include_router(market_data_router)
app.include_router(quant_router)
app.include_router(research_router)
app.include_router(paper_router)
app.include_router(realtime_router)
app.include_router(ml_router)
app.include_router(similarity_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "phase": 9,
        "dataSource": "PERSISTENT_AND_SIMULATOR",
        "livePathSealed": True,
        "quantEngine": "ENABLED",
        "backtestingEngine": "ENABLED",
        "paperEngine": "ENABLED",
        "realtimeGateway": "ENABLED",
        "mlArchitecture": "ENABLED",
        "calibration": "PLATT+ISOTONIC",
        "driftMonitor": "PSI+ZSCORE+VARRATIO",
        "evidenceMemory": "COSINE_SIMILARITY",
        "patternLibrary": "8_PATTERNS",
        "brokerIntegration": "OPENALGO_GATED",
        "liveTrading": "DISABLED_BY_DEFAULT",
    }
