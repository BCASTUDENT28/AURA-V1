"""
backend/app/main.py

FastAPI application entry point.
Start with: uvicorn backend.app.main:app --reload
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes.decisions import router as decisions_router
from backend.app.api.routes.market_data import router as market_data_router

app = FastAPI(
    title="AURA Backend — Phase 2",
    description=(
        "Decision, risk, cost computation, and canonical market data engine. "
        "Persistent research data, instrument master, and dataset lineage. "
        "No live broker connections. No Angel One / Groww credentials."
    ),
    version="2.0.0",
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

app.include_router(decisions_router)
app.include_router(market_data_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "phase": 2,
        "dataSource": "PERSISTENT_AND_SIMULATOR",
        "livePathSealed": True,
        "masterInstruments": 10,
    }
