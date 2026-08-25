"""
backend/tests/test_walk_forward.py

Tests for Walk-Forward Optimization Engine.
Verifies:
- Rolling window generation (In-Sample train & Out-Of-Sample test)
- Best parameter selection per train window
- Stitching of out-of-sample performance metrics
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.data.simulator import bars_of
from backend.app.research.walk_forward import WalkForwardOptimizer


def test_walk_forward_execution():
    """Run rolling walk-forward optimization over historical bars."""
    bars = bars_of("NIFTY", "1D")
    param_grid = [
        {"fast": 9, "slow": 21, "rr": 2.0},
        {"fast": 5, "slow": 15, "rr": 1.5},
    ]

    optimizer = WalkForwardOptimizer(
        strategy_id="ma_cross",
        param_grid=param_grid,
        train_bars=150,
        test_bars=40,
        step_bars=40,
    )

    res = optimizer.run("NIFTY", bars)

    assert res.strategyId == "ma_cross"
    assert res.symbol == "NIFTY"
    assert res.totalWindows >= 5
    assert len(res.windows) == res.totalWindows

    for win in res.windows:
        assert win.windowNum > 0
        assert win.trainEndMs > win.trainStartMs
        assert win.testStartMs > win.trainEndMs
        assert win.bestParams in param_grid

    assert res.combinedOutOfSampleMetrics is not None
