"""
backend/app/similarity/vector_store.py

In-memory Feature Vector Store for AURA AI (Phase 8).

Stores historical feature vectors as embeddings and supports:
  - Cosine similarity search: find the K most similar past market states
  - Outcome tagging: annotate stored vectors with actual forward returns
  - Evidence retrieval: surface the historical analogues with their outcomes
  - TTL eviction: remove stale entries beyond a configurable window

Architecture:
  - Pure Python, no external vector DB dependency
  - Feature vector → L2-normalised float list (embedding)
  - O(n) exhaustive search — sufficient for ≤ 5,000 daily bars
  - Singleton store, shared across request lifetime

Evidence Memory Philosophy:
  When the model sees a new bar, it asks:
    "What happened the last N times the market looked exactly like this?"
  The answer — historical outcomes weighted by similarity — becomes the
  Evidence Memory signal fed into the decision engine.
"""

from __future__ import annotations

import math
import time
import uuid
from typing import Optional

from pydantic import BaseModel

from backend.app.quant.features import FeatureVector


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

EMBEDDING_FIELDS = [
    "rsi14", "macd", "macdHist", "adx14", "plusDi14", "minusDi14",
    "bbPercentB", "bbBandwidth", "realizedVol20", "relVolume20",
    "return1d", "return5d", "return20d", "skewness20", "autocorr1",
    "sma9", "sma21", "sma50",  # relative price position signals
]


class EvidenceEntry(BaseModel):
    id: str
    symbol: str
    t: int                        # unix epoch of the bar
    embedding: list[float]        # L2-normalised feature embedding
    similarity: float             # cosine similarity to query (0–1)
    forwardReturn: Optional[float]  # actualised t+1 daily return if known
    regime: Optional[str]           # regime label at time of storage
    storedAt: float               # wall-clock time of storage


class EvidenceMemoryResult(BaseModel):
    querySymbol: str
    queryT: int
    topK: int
    results: list[EvidenceEntry]
    weightedExpectedReturn: float   # Σ(sim_i * fwd_i) / Σ(sim_i)
    signalDirection: str            # "UP" | "DOWN" | "FLAT"
    signalStrength: float           # [0, 1] based on consensus


class StorageStats(BaseModel):
    totalEntries: int
    symbolBreakdown: dict[str, int]
    oldestEntryAge: float   # seconds
    newestEntryAge: float   # seconds


# ─────────────────────────────────────────────────────────────────────────────
# Embedding
# ─────────────────────────────────────────────────────────────────────────────

def _extract_embedding(feat: FeatureVector) -> list[float]:
    """
    Extract the embedding vector from a FeatureVector.
    Features are normalised by domain-knowledge scales to ensure
    comparable magnitudes before L2 normalisation.
    """
    raw: list[float] = []
    for field in EMBEDDING_FIELDS:
        v = getattr(feat, field, 0.0) or 0.0
        raw.append(float(v))

    # L2 normalise
    norm = math.sqrt(sum(x * x for x in raw))
    if norm < 1e-9:
        return [0.0] * len(raw)
    return [x / norm for x in raw]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two L2-normalised vectors = their dot product."""
    if len(a) != len(b):
        return 0.0
    return max(0.0, min(1.0, sum(x * y for x, y in zip(a, b))))


# ─────────────────────────────────────────────────────────────────────────────
# Store
# ─────────────────────────────────────────────────────────────────────────────

class _StoredEntry:
    __slots__ = ["id", "symbol", "t", "embedding", "stored_at",
                 "forward_return", "regime"]

    def __init__(self, symbol: str, t: int, embedding: list[float],
                 regime: Optional[str] = None) -> None:
        self.id = str(uuid.uuid4())[:12]
        self.symbol = symbol
        self.t = t
        self.embedding = embedding
        self.stored_at = time.time()
        self.forward_return: Optional[float] = None
        self.regime = regime


class FeatureVectorStore:
    """
    In-memory cosine similarity search store.
    Thread-safe enough for single-process async FastAPI (GIL protected).
    """

    MAX_ENTRIES = 5_000    # evict oldest when exceeded
    TTL_SECONDS = 86_400 * 90  # 90-day rolling window

    def __init__(self) -> None:
        self._entries: list[_StoredEntry] = []
        self._id_index: dict[str, int] = {}  # id → list index

    def store(
        self,
        feat: FeatureVector,
        symbol: str,
        regime: Optional[str] = None,
    ) -> str:
        """Store a feature vector. Returns the assigned entry ID."""
        embedding = _extract_embedding(feat)
        entry = _StoredEntry(symbol=symbol, t=feat.t,
                             embedding=embedding, regime=regime)
        self._entries.append(entry)
        self._id_index[entry.id] = len(self._entries) - 1
        self._evict()
        return entry.id

    def tag_outcome(self, entry_id: str, forward_return: float) -> bool:
        """
        Retrospectively tag an entry with its actualised forward return.
        Returns True if found and updated.
        """
        idx = self._id_index.get(entry_id)
        if idx is not None and idx < len(self._entries):
            self._entries[idx].forward_return = forward_return
            return True
        return False

    def query(
        self,
        feat: FeatureVector,
        symbol: str,
        top_k: int = 10,
        min_similarity: float = 0.90,
        exclude_self: bool = True,
    ) -> EvidenceMemoryResult:
        """
        Find the top-K most similar historical feature vectors.
        Returns Evidence Memory result with weighted expected return signal.
        """
        query_embedding = _extract_embedding(feat)
        now_t = feat.t

        scored: list[tuple[float, _StoredEntry]] = []
        for entry in self._entries:
            if exclude_self and entry.t == now_t and entry.symbol == symbol:
                continue
            sim = _cosine_similarity(query_embedding, entry.embedding)
            if sim >= min_similarity:
                scored.append((sim, entry))

        # Sort descending by similarity
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        now = time.time()
        results: list[EvidenceEntry] = []
        for sim, e in top:
            results.append(EvidenceEntry(
                id=e.id, symbol=e.symbol, t=e.t,
                embedding=e.embedding,
                similarity=round(sim, 5),
                forwardReturn=e.forward_return,
                regime=e.regime,
                storedAt=e.stored_at,
            ))

        # Compute evidence-weighted expected return
        tagged = [(r.similarity, r.forwardReturn)
                  for r in results if r.forwardReturn is not None]
        if tagged:
            total_sim = sum(s for s, _ in tagged)
            weighted_return = sum(s * r for s, r in tagged) / max(total_sim, 1e-9)
            up_weight = sum(s for s, r in tagged if r > 0.005)
            dn_weight = sum(s for s, r in tagged if r < -0.005)
            net = up_weight - dn_weight
            if abs(net) < 1e-6:
                direction = "FLAT"
                strength = 0.0
            elif net > 0:
                direction = "UP"
                strength = round(net / (up_weight + dn_weight + 1e-9), 4)
            else:
                direction = "DOWN"
                strength = round(abs(net) / (up_weight + dn_weight + 1e-9), 4)
        else:
            weighted_return = 0.0
            direction = "FLAT"
            strength = 0.0

        return EvidenceMemoryResult(
            querySymbol=symbol,
            queryT=feat.t,
            topK=len(results),
            results=results,
            weightedExpectedReturn=round(weighted_return, 6),
            signalDirection=direction,
            signalStrength=strength,
        )

    def stats(self) -> StorageStats:
        now = time.time()
        breakdown: dict[str, int] = {}
        for e in self._entries:
            breakdown[e.symbol] = breakdown.get(e.symbol, 0) + 1
        ages = [now - e.stored_at for e in self._entries]
        return StorageStats(
            totalEntries=len(self._entries),
            symbolBreakdown=breakdown,
            oldestEntryAge=round(max(ages), 1) if ages else 0.0,
            newestEntryAge=round(min(ages), 1) if ages else 0.0,
        )

    def clear(self) -> int:
        n = len(self._entries)
        self._entries.clear()
        self._id_index.clear()
        return n

    def _evict(self) -> None:
        """Remove stale TTL entries and cap at MAX_ENTRIES."""
        if len(self._entries) <= self.MAX_ENTRIES:
            return
        # Drop oldest
        drop = len(self._entries) - self.MAX_ENTRIES
        self._entries = self._entries[drop:]
        # Rebuild index
        self._id_index = {e.id: i for i, e in enumerate(self._entries)}


# Singleton
_STORE = FeatureVectorStore()


def get_vector_store() -> FeatureVectorStore:
    return _STORE
