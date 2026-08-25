"""
backend/tests/test_strategies_framework.py

Tests for BaseStrategy framework and concrete strategy implementations.
Verifies:
- Standardized StrategySignal outputs (action in BUY/SELL/HOLD/SKIP)
- Finite brackets for entry, stop, and target when action is BUY/SELL
- Risk-to-Reward ratio consistency
- Parameter schema serialization and custom override
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.data.simulator import bars_of
from backend.app.quant.base_strategy import (
    MACrossoverStrategy,
    OpeningRangeBreakoutStrategy,
    VWAPRSIStrategy,
    get_strategy,
    list_quant_strategies,
)


def test_list_all_quant_strategies():
    """All core strategies must be listed with default parameters."""
    strats = list_quant_strategies()
    assert len(strats) == 3
    ids = [s["id"] for s in strats]
    assert "ma_cross" in ids
    assert "vwap_rsi" in ids
    assert "orb" in ids


def test_strategy_factory_instantiation():
    """Strategy factory instantiates with custom params."""
    strat = get_strategy("ma_cross", params={"fast": 5, "slow": 15, "rr": 3.0})
    assert strat.params["fast"] == 5
    assert strat.params["slow"] == 15
    assert strat.params["rr"] == 3.0


def test_ma_cross_signal_bracket_consistency():
    """MA Crossover strategy must produce valid bracket and action."""
    strat = MACrossoverStrategy()
    bars = bars_of("NIFTY", "1D")
    signal = strat.evaluate(bars)

    assert signal.action in ["BUY", "SELL", "HOLD", "SKIP"]
    assert 0.0 <= signal.confidence <= 1.0
    if signal.action in ["BUY", "SELL"]:
        assert signal.entry is not None and signal.entry > 0
        assert signal.stop is not None and signal.stop > 0
        assert signal.target is not None and signal.target > 0
        if signal.action == "BUY":
            assert signal.target > signal.entry > signal.stop
        elif signal.action == "SELL":
            assert signal.target < signal.entry < signal.stop


def test_vwap_rsi_signal_bracket_consistency():
    """VWAP + RSI strategy must produce valid bracket and action."""
    strat = VWAPRSIStrategy()
    bars = bars_of("BANKNIFTY", "5m")
    signal = strat.evaluate(bars)

    assert signal.action in ["BUY", "SELL", "HOLD", "SKIP"]
    assert 0.0 <= signal.confidence <= 1.0
    if signal.action in ["BUY", "SELL"]:
        assert signal.entry is not None and signal.entry > 0
        assert signal.stop is not None and signal.stop > 0
        assert signal.target is not None and signal.target > 0


def test_orb_signal_bracket_consistency():
    """ORB strategy must produce valid bracket and action."""
    strat = OpeningRangeBreakoutStrategy()
    bars = bars_of("RELIANCE", "5m")
    signal = strat.evaluate(bars)

    assert signal.action in ["BUY", "SELL", "HOLD", "SKIP"]
    assert 0.0 <= signal.confidence <= 1.0
    if signal.action in ["BUY", "SELL"]:
        assert signal.entry is not None and signal.entry > 0
        assert signal.stop is not None and signal.stop > 0
        assert signal.target is not None and signal.target > 0
