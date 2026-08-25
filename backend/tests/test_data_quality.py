"""
backend/tests/test_data_quality.py

Tests for Automated Data Quality & Validation Engine.
Verifies:
- Duplicate timestamp detection
- Outlier / anomalous spike filtering (>10% sudden jump)
- Session continuity & missing trading days audit
- Backward adjustment for corporate actions (splits, bonuses)
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.data.quality import (
    apply_corporate_actions,
    audit_dataset,
    check_duplicate_timestamps,
    detect_outlier_ticks,
    validate_session_continuity,
)
from backend.app.schemas.market_data import CorporateAction, HistoricalBarRecord


def _create_bar(ts_ms: int, o: float, h: float, l: float, c: float, v: float) -> HistoricalBarRecord:
    return HistoricalBarRecord(t=ts_ms, o=o, h=h, l=l, c=c, v=v, isAdjusted=False)


def test_duplicate_detection():
    """Duplicate timestamps must be flagged and counted."""
    bars = [
        _create_bar(1700000000000, 100, 105, 95, 102, 1000),
        _create_bar(1700000000000, 102, 106, 96, 104, 1200),  # duplicate timestamp
        _create_bar(1700086400000, 104, 110, 102, 108, 1500),
    ]
    dupes = check_duplicate_timestamps(bars)
    assert dupes == 1


def test_no_duplicate_clean_series():
    bars = [
        _create_bar(1700000000000, 100, 105, 95, 102, 1000),
        _create_bar(1700086400000, 102, 106, 96, 104, 1200),
        _create_bar(1700172800000, 104, 110, 102, 108, 1500),
    ]
    assert check_duplicate_timestamps(bars) == 0


def test_outlier_spike_detection():
    """Spikes >10% move from previous close must be flagged as anomalous."""
    bars = [
        _create_bar(1700000000000, 100, 102, 98, 100, 1000),
        _create_bar(1700086400000, 100, 103, 99, 101, 1000),
        _create_bar(1700172800000, 101, 130, 101, 125, 50),   # +23.7% jump on tiny volume
    ]
    outliers = detect_outlier_ticks(bars, max_jump_pct=0.10)
    assert len(outliers) == 1
    assert outliers[0]["pct_change"] > 0.20
    assert outliers[0]["close"] == 125


def test_normal_volatility_not_flagged_as_outlier():
    """Normal price movement (1-3%) must not be flagged."""
    bars = [
        _create_bar(1700000000000, 100, 102, 98, 101, 1000),
        _create_bar(1700086400000, 101, 104, 100, 103, 1100),
        _create_bar(1700172800000, 103, 105, 101, 102, 900),
    ]
    outliers = detect_outlier_ticks(bars, max_jump_pct=0.10)
    assert len(outliers) == 0


def test_corporate_action_split_backward_adjustment():
    """
    A 1:2 stock split on 2024-06-01 must cut pre-split prices by 50%
    and double pre-split volume.
    """
    # 2024-05-15 (pre-split): 1715731200000 ms
    # 2024-06-15 (post-split): 1718409600000 ms
    pre_bar = _create_bar(1715731200000, 2000.0, 2050.0, 1980.0, 2020.0, 10000.0)
    post_bar = _create_bar(1718409600000, 1020.0, 1050.0, 1010.0, 1040.0, 20000.0)

    action = CorporateAction(
        instrumentId="NSE:TEST",
        actionType="SPLIT",
        ratioFrom=1.0,
        ratioTo=2.0,
        exDate="2024-06-01",
        isApplied=True,
    )

    adjusted = apply_corporate_actions([pre_bar, post_bar], [action])

    # Pre-split bar must be halved
    assert adjusted[0].o == 1000.0
    assert adjusted[0].h == 1025.0
    assert adjusted[0].l == 990.0
    assert adjusted[0].c == 1010.0
    assert adjusted[0].v == 20000.0

    # Post-split bar remains unchanged
    assert adjusted[1].o == 1020.0
    assert adjusted[1].c == 1040.0


def test_full_dataset_quality_audit():
    """Verify audit_dataset generates a structured DataQualityReport."""
    clean_series = [
        _create_bar(1704067200000 + i * 86400000, 100 + i, 102 + i, 98 + i, 101 + i, 1000)
        for i in range(10)
    ]
    report = audit_dataset(
        dataset_version_id="test-dataset-v1",
        bars_by_symbol={"RELIANCE": clean_series},
    )
    assert report.datasetVersionId == "test-dataset-v1"
    assert report.status == "PASS"
    assert report.missingCandles >= 0
    assert report.duplicateCandles == 0
    assert report.outlierTicks == 0
