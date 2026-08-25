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

app = FastAPI(
    title="AURA Backend — Phase 1",
    description=(
        "Decision, risk, and cost computation engine. "
        "Market data is synthetic (SIMULATOR). "
        "No live broker connections. No Angel One / Groww credentials."
    ),
    version="1.0.0",
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


@app.get("/health")
def health():
    return {"status": "ok", "phase": 1, "dataSource": "SIMULATOR", "livePathSealed": True}
