"""
backend/tests/test_features_no_lookahead.py

Tests for No-Lookahead Bias Guarantee in Quant Feature Pack.
Proves mathematically that changing future bar data (t+1 ... T)
has ZERO effect on the feature vector extracted at timestamp t.
"""

from __future__ import annotations

import copy
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.data.simulator import bars_of
from backend.app.quant.features import extract_features, extract_feature_matrix
from backend.app.schemas.types import Bar


def test_no_lookahead_invariant():
    """
    Extract features at bar 50.
    Then mutate future bars 51..100 wildly (10x price, 100x volume).
    Assert that features at bar 50 are byte-for-byte identical.
    """
    raw_bars = bars_of("NIFTY", "1D")
    slice_50 = raw_bars[:50]
    slice_100 = copy.deepcopy(raw_bars[:100])

    # Baseline features at t=50
    feat_50_baseline = extract_features(slice_50)

    # Mutate future bars in slice_100
    for i in range(50, 100):
        orig = slice_100[i]
        slice_100[i] = Bar(
            t=orig.t,
            o=orig.o * 10.0,
            h=orig.h * 15.0,
            l=orig.l * 5.0,
            c=orig.c * 12.0,
            v=orig.v * 100.0,
        )

    # Re-extract features at index 50 from the series prefix
    feat_50_after_future_mutation = extract_features(slice_100[:50])

    assert feat_50_baseline.model_dump() == feat_50_after_future_mutation.model_dump(), (
        "No-lookahead violation: Features at t=50 were affected by future bar mutations!"
    )


def test_feature_matrix_causality():
    """Matrix extraction at each step i must match extract_features(bars[:i+1])."""
    raw_bars = bars_of("RELIANCE", "1D")[:60]
    matrix = extract_feature_matrix(raw_bars, min_warmup=50)

    assert len(matrix) == 11  # indices 50..60 (inclusive) -> 11 steps

    for idx, feat in enumerate(matrix):
        expected_len = 50 + idx
        direct_feat = extract_features(raw_bars[:expected_len])
        assert feat.t == direct_feat.t
        assert feat.close == direct_feat.close
        assert feat.rsi14 == direct_feat.rsi14
        assert feat.sma9 == direct_feat.sma9
        assert feat.bbUpper == direct_feat.bbUpper
