"""
tests/test_similarity.py

Phase 8 — Similarity & Evidence Memory tests.
Tests vector store, cosine similarity, outcome tagging, and pattern library.
"""

from __future__ import annotations

import math
import pytest

from backend.app.quant.features import FeatureVector
from backend.app.similarity.vector_store import (
    FeatureVectorStore,
    _extract_embedding,
    _cosine_similarity,
    EvidenceMemoryResult,
)
from backend.app.similarity.pattern_library import (
    scan_patterns,
    PatternMatch,
    ACTIVATION_THRESHOLD,
)


# ─────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────

def _make_feat(**overrides) -> FeatureVector:
    base = dict(
        t=1_700_000_000,
        close=1000.0,
        sma9=1000.0, sma21=1000.0, sma50=1000.0, sma200=1000.0,
        ema9=1000.0, ema21=1000.0, ema50=1000.0,
        rsi14=50.0,
        macd=0.0, macdSignal=0.0, macdHist=0.0,
        atr14=10.0,
        adx14=15.0, plusDi14=18.0, minusDi14=18.0,
        bbUpper=1020.0, bbLower=980.0, bbMid=1000.0,
        bbPercentB=0.5, bbBandwidth=0.04,
        realizedVol20=0.15,
        vwap20=1000.0, vwapDevAtr=0.0, volumeZ20=0.0, relVolume20=1.0,
        return1d=0.0, return5d=0.0, return20d=0.0,
        skewness20=0.0, autocorr1=0.0,
    )
    base.update(overrides)
    return FeatureVector(**base)


# ─────────────────────────────────────────────────────────
# Embedding
# ─────────────────────────────────────────────────────────

class TestEmbedding:

    def test_l2_norm_is_one(self):
        feat = _make_feat(rsi14=65.0, adx14=30.0)
        emb = _extract_embedding(feat)
        norm = math.sqrt(sum(x * x for x in emb))
        assert abs(norm - 1.0) < 1e-5, f"Embedding L2 norm should be 1.0, got {norm}"

    def test_all_zeros_returns_zero_vector(self):
        feat = _make_feat(rsi14=0.0, macd=0.0, macdHist=0.0, adx14=0.0,
                          plusDi14=0.0, minusDi14=0.0, bbPercentB=0.0,
                          bbBandwidth=0.0, realizedVol20=0.0, relVolume20=0.0,
                          return1d=0.0, return5d=0.0, return20d=0.0,
                          skewness20=0.0, autocorr1=0.0,
                          sma9=0.0, sma21=0.0, sma50=0.0)
        emb = _extract_embedding(feat)
        assert all(x == 0.0 for x in emb)

    def test_different_features_different_embeddings(self):
        f1 = _make_feat(rsi14=30.0, adx14=10.0)
        f2 = _make_feat(rsi14=75.0, adx14=40.0)
        e1 = _extract_embedding(f1)
        e2 = _extract_embedding(f2)
        assert e1 != e2

    def test_cosine_identical_vectors(self):
        feat = _make_feat(rsi14=60.0, adx14=25.0)
        emb = _extract_embedding(feat)
        sim = _cosine_similarity(emb, emb)
        assert abs(sim - 1.0) < 1e-5

    def test_cosine_in_0_1(self):
        f1 = _make_feat(rsi14=30.0)
        f2 = _make_feat(rsi14=70.0)
        e1 = _extract_embedding(f1)
        e2 = _extract_embedding(f2)
        sim = _cosine_similarity(e1, e2)
        assert 0.0 <= sim <= 1.0


# ─────────────────────────────────────────────────────────
# Vector Store
# ─────────────────────────────────────────────────────────

class TestVectorStore:

    def _fresh(self) -> FeatureVectorStore:
        return FeatureVectorStore()

    def test_store_returns_string_id(self):
        vs = self._fresh()
        feat = _make_feat()
        entry_id = vs.store(feat, symbol="NIFTY")
        assert isinstance(entry_id, str)
        assert len(entry_id) > 0

    def test_store_increments_count(self):
        vs = self._fresh()
        for i in range(5):
            feat = _make_feat(t=1_700_000_000 + i)
            vs.store(feat, symbol="NIFTY")
        assert vs.stats().totalEntries == 5

    def test_tag_outcome_updates_entry(self):
        vs = self._fresh()
        feat = _make_feat()
        entry_id = vs.store(feat, symbol="NIFTY")
        success = vs.tag_outcome(entry_id, 0.015)
        assert success is True

    def test_tag_outcome_wrong_id_returns_false(self):
        vs = self._fresh()
        success = vs.tag_outcome("nonexistent_id", 0.01)
        assert success is False

    def test_query_returns_evidence_result(self):
        vs = self._fresh()
        # Store some vectors
        for i in range(5):
            feat = _make_feat(t=1_700_000_000 + i, rsi14=55.0 + i)
            vs.store(feat, symbol="NIFTY")
        query_feat = _make_feat(t=1_700_000_999, rsi14=57.0)
        result = vs.query(query_feat, symbol="NIFTY", top_k=3, min_similarity=0.0)
        assert isinstance(result, EvidenceMemoryResult)
        assert result.topK <= 3

    def test_query_similar_vectors_high_similarity(self):
        vs = self._fresh()
        feat_a = _make_feat(rsi14=60.0, adx14=28.0, t=1_000_000_001)
        feat_b = _make_feat(rsi14=60.5, adx14=27.8, t=1_000_000_002)
        vs.store(feat_a, symbol="NIFTY")
        vs.store(feat_b, symbol="NIFTY")

        query = _make_feat(rsi14=60.0, adx14=28.0, t=1_000_000_999)
        result = vs.query(query, symbol="NIFTY", top_k=5, min_similarity=0.90)
        if result.results:
            for r in result.results:
                assert r.similarity >= 0.90

    def test_query_direction_with_tagged_outcomes(self):
        vs = self._fresh()
        # Store 5 bullish analogues with positive outcomes
        for i in range(5):
            feat = _make_feat(t=1_700_000_000 + i, rsi14=65.0)
            eid = vs.store(feat, symbol="NIFTY")
            vs.tag_outcome(eid, 0.02)  # 2% positive forward return

        query = _make_feat(t=1_700_000_999, rsi14=65.0)
        result = vs.query(query, symbol="NIFTY", top_k=5, min_similarity=0.0)
        assert result.weightedExpectedReturn > 0.0
        assert result.signalDirection == "UP"

    def test_query_direction_bearish_outcomes(self):
        vs = self._fresh()
        for i in range(5):
            feat = _make_feat(t=1_700_000_000 + i, rsi14=30.0)
            eid = vs.store(feat, symbol="NIFTY")
            vs.tag_outcome(eid, -0.025)

        query = _make_feat(t=1_700_000_999, rsi14=30.0)
        result = vs.query(query, symbol="NIFTY", top_k=5, min_similarity=0.0)
        assert result.weightedExpectedReturn < 0.0
        assert result.signalDirection == "DOWN"

    def test_clear_resets_store(self):
        vs = self._fresh()
        for i in range(10):
            vs.store(_make_feat(t=i), symbol="NIFTY")
        n = vs.clear()
        assert n == 10
        assert vs.stats().totalEntries == 0

    def test_stats_symbol_breakdown(self):
        vs = self._fresh()
        for i in range(3):
            vs.store(_make_feat(t=i), symbol="NIFTY")
        for i in range(2):
            vs.store(_make_feat(t=i + 100), symbol="BANKNIFTY")
        stats = vs.stats()
        assert stats.symbolBreakdown.get("NIFTY") == 3
        assert stats.symbolBreakdown.get("BANKNIFTY") == 2

    def test_max_entries_eviction(self):
        vs = self._fresh()
        vs.MAX_ENTRIES = 10
        for i in range(15):
            vs.store(_make_feat(t=i), symbol="NIFTY")
        assert vs.stats().totalEntries <= 10


# ─────────────────────────────────────────────────────────
# Pattern Library
# ─────────────────────────────────────────────────────────

class TestPatternLibrary:

    def test_scan_returns_8_patterns(self):
        feat = _make_feat()
        matches = scan_patterns(feat)
        assert len(matches) == 8

    def test_all_match_scores_in_0_1(self):
        feat = _make_feat()
        for m in scan_patterns(feat):
            assert 0.0 <= m.matchScore <= 1.0, f"{m.name} score {m.matchScore} out of range"

    def test_sorted_descending(self):
        feat = _make_feat()
        matches = scan_patterns(feat)
        for i in range(len(matches) - 1):
            assert matches[i].matchScore >= matches[i + 1].matchScore

    def test_momentum_surge_activated_on_strong_trend(self):
        feat = _make_feat(
            adx14=35.0, plusDi14=30.0, minusDi14=8.0,
            relVolume20=2.2, bbPercentB=0.88
        )
        matches = scan_patterns(feat)
        surge = next(m for m in matches if m.name == "MOMENTUM_SURGE")
        assert surge.activated, f"Expected MOMENTUM_SURGE activated, score={surge.matchScore}"
        assert surge.expectedBias == "BULLISH"

    def test_panic_capitulation_activated_on_crash(self):
        feat = _make_feat(
            rsi14=22.0, return1d=-0.04, relVolume20=3.0, bbPercentB=0.05
        )
        matches = scan_patterns(feat)
        cap = next(m for m in matches if m.name == "PANIC_CAPITULATION")
        assert cap.activated, f"Expected PANIC_CAPITULATION activated, score={cap.matchScore}"

    def test_coiling_spring_activated_on_vol_compression(self):
        feat = _make_feat(
            bbBandwidth=0.02, adx14=10.0, relVolume20=0.5, realizedVol20=0.08
        )
        matches = scan_patterns(feat)
        spring = next(m for m in matches if m.name == "COILING_SPRING")
        assert spring.activated, f"Expected COILING_SPRING activated, score={spring.matchScore}"

    def test_each_pattern_has_conditions(self):
        feat = _make_feat()
        for m in scan_patterns(feat):
            assert len(m.conditions) >= 3, f"{m.name} has too few conditions"
            for c in m.conditions:
                assert 0.0 <= c.score <= 1.0

    def test_activation_threshold_consistent(self):
        feat = _make_feat()
        for m in scan_patterns(feat):
            assert m.activated == (m.matchScore >= ACTIVATION_THRESHOLD)

    def test_condition_weights_sum_to_one(self):
        feat = _make_feat()
        for m in scan_patterns(feat):
            total = sum(c.weight for c in m.conditions)
            assert abs(total - 1.0) < 1e-3, f"{m.name} weights sum to {total}"

    def test_bear_continuation_biased_correctly(self):
        feat = _make_feat(
            adx14=28.0, plusDi14=8.0, minusDi14=28.0, return5d=-0.05, rsi14=38.0
        )
        matches = scan_patterns(feat)
        bear = next(m for m in matches if m.name == "BEAR_CONTINUATION")
        assert bear.expectedBias == "BEARISH"
        assert bear.matchScore > 0.5
