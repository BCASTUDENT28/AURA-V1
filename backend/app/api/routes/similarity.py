"""
backend/app/api/routes/similarity.py

Phase 8 Similarity + Evidence Memory API:
  POST /api/similarity/store          – store a feature vector in evidence memory
  POST /api/similarity/query          – find top-K similar historical states
  POST /api/similarity/tag-outcome    – retroactively tag a stored entry with forward return
  GET  /api/similarity/stats          – vector store statistics
  DELETE /api/similarity/clear        – clear the vector store
  POST /api/similarity/patterns       – scan all market patterns against current bar
  GET  /api/similarity/patterns/list  – list all registered pattern definitions
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.data.store import get_market_store
from backend.app.quant.features import extract_features

from backend.app.similarity.vector_store import (
    get_vector_store,
    EvidenceMemoryResult,
    StorageStats,
)
from backend.app.similarity.pattern_library import scan_patterns, PatternMatch, ACTIVATION_THRESHOLD

router = APIRouter(prefix="/api/similarity", tags=["Similarity & Evidence Memory (Phase 8)"])


# ─── Request Models ───────────────────────────────────────────────────────────

class StoreRequest(BaseModel):
    symbol: str
    timeframe: str = "1D"
    regime: Optional[str] = None


class QueryRequest(BaseModel):
    symbol: str
    timeframe: str = "1D"
    topK: int = 10
    minSimilarity: float = 0.88


class TagOutcomeRequest(BaseModel):
    entryId: str
    forwardReturn: float


class PatternScanRequest(BaseModel):
    symbol: str
    timeframe: str = "1D"
    activatedOnly: bool = False


class PatternDefinitionResponse(BaseModel):
    patternId: str
    name: str
    description: str
    expectedBias: str
    impliedAction: str
    activationThreshold: float


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/store")
def store_feature_vector(req: StoreRequest):
    """
    Store the current bar's feature vector in the evidence memory.
    Returns the assigned entry ID for later outcome tagging.
    """
    store = get_market_store()
    bars = store.bars_of(req.symbol, req.timeframe)
    if not bars or len(bars) < 21:
        raise HTTPException(status_code=404,
                            detail=f"Insufficient bars for {req.symbol}")
    feat = extract_features(bars)
    vs = get_vector_store()
    entry_id = vs.store(feat, symbol=req.symbol, regime=req.regime)
    return {
        "ok": True,
        "entryId": entry_id,
        "symbol": req.symbol,
        "t": feat.t,
        "totalStored": vs.stats().totalEntries,
    }


@router.post("/query", response_model=EvidenceMemoryResult)
def query_evidence_memory(req: QueryRequest):
    """
    Find the top-K most similar historical market states.
    Returns weighted expected return and directional signal from evidence.
    """
    if req.topK < 1 or req.topK > 100:
        raise HTTPException(status_code=422, detail="topK must be in [1, 100]")
    if not (0.0 <= req.minSimilarity <= 1.0):
        raise HTTPException(status_code=422, detail="minSimilarity must be in [0.0, 1.0]")

    store = get_market_store()
    bars = store.bars_of(req.symbol, req.timeframe)
    if not bars or len(bars) < 21:
        raise HTTPException(status_code=404,
                            detail=f"Insufficient bars for {req.symbol}")
    feat = extract_features(bars)
    vs = get_vector_store()
    return vs.query(feat, symbol=req.symbol,
                    top_k=req.topK, min_similarity=req.minSimilarity)


@router.post("/tag-outcome")
def tag_outcome(req: TagOutcomeRequest):
    """
    Retroactively tag a stored evidence entry with its actualised forward return.
    Use this after the bar closes to build the labelled evidence library.
    """
    vs = get_vector_store()
    success = vs.tag_outcome(req.entryId, req.forwardReturn)
    if not success:
        raise HTTPException(status_code=404,
                            detail=f"Entry '{req.entryId}' not found")
    return {"ok": True, "entryId": req.entryId, "forwardReturn": req.forwardReturn}


@router.get("/stats", response_model=StorageStats)
def get_vector_store_stats():
    """Return statistics about the evidence memory store."""
    return get_vector_store().stats()


@router.delete("/clear")
def clear_vector_store():
    """Clear all entries from the evidence memory store."""
    n = get_vector_store().clear()
    return {"ok": True, "clearedEntries": n}


# ─── Pattern Library ─────────────────────────────────────────────────────────

@router.post("/patterns", response_model=list[PatternMatch])
def scan_market_patterns(req: PatternScanRequest):
    """
    Scan all 8 market patterns against the current bar.
    Returns ranked list of patterns with match scores and condition breakdowns.
    """
    store = get_market_store()
    bars = store.bars_of(req.symbol, req.timeframe)
    if not bars or len(bars) < 21:
        raise HTTPException(status_code=404,
                            detail=f"Insufficient bars for {req.symbol}")
    feat = extract_features(bars)
    matches = scan_patterns(feat)
    if req.activatedOnly:
        matches = [m for m in matches if m.activated]
    return matches


@router.get("/patterns/list", response_model=list[PatternDefinitionResponse])
def list_pattern_definitions():
    """List all registered pattern definitions with their metadata."""
    from backend.app.similarity.pattern_library import _PATTERN_REGISTRY
    return [
        PatternDefinitionResponse(
            patternId=p["id"],
            name=p["name"],
            description=p["description"],
            expectedBias=p["bias"],
            impliedAction=p["action"],
            activationThreshold=ACTIVATION_THRESHOLD,
        )
        for p in _PATTERN_REGISTRY
    ]
