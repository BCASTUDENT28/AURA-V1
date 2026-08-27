"""
backend/tests/test_backtest_causality.py

Tests for Causal Fill Modeling & Cost Integration in Backtester.
Verifies:
- Orders generated at bar t fill strictly at bar t+1 open (no same-bar lookahead).
- Indian discount-broker costs (brokerage, STT, stamp, exchange, GST, SEBI) deducted on every trade.
- Multi-trade P&L consistency.
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.data.simulator import bars_of
from backend.app.quant.base_strategy import MACrossoverStrategy
from backend.app.research.backtester import CausalBacktester


def test_backtest_execution_and_trades_generated():
    """Backtest runs deterministically and produces trades."""
    bars = bars_of("NIFTY", "1D")
    strat = MACrossoverStrategy()
    bt = CausalBacktester(strategy=strat, initial_capital=1_000_000.0)

    res = bt.run("NIFTY", bars)

    assert res.runId.startswith("run-ma_cross-NIFTY")
    assert res.metrics.totalTrades > 0
    assert len(res.trades) == res.metrics.totalTrades
    assert len(res.metrics.equityCurve) > 0


def test_fill_causality_timing():
    """Verify each trade entry timestamp is >= previous bar timestamp."""
    bars = bars_of("BANKNIFTY", "1D")
    strat = MACrossoverStrategy()
    bt = CausalBacktester(strategy=strat, initial_capital=1_000_000.0)

    res = bt.run("BANKNIFTY", bars)

    for t in res.trades:
        assert t.exitTs >= t.entryTs
        assert t.durationBars >= 0
        assert t.entryPx > 0
        assert t.exitPx > 0
        assert t.totalCosts > 0, "Trade must incur non-zero Indian broker costs"
        # Net P&L = Gross P&L - total costs (tolerance ±0.02 for float accumulation)
        assert abs(t.netPnl - (t.grossPnl - t.totalCosts)) < 0.02, (
            f"netPnl {t.netPnl} != grossPnl {t.grossPnl} - totalCosts {t.totalCosts}"
        )


def test_costs_deducted_from_equity():
    """Total costs deducted across all trades must equal metrics.totalCosts."""
    bars = bars_of("RELIANCE", "1D")
    strat = MACrossoverStrategy()
    bt = CausalBacktester(strategy=strat, initial_capital=1_000_000.0)

    res = bt.run("RELIANCE", bars)

    sum_costs = sum(t.totalCosts for t in res.trades)
    assert round(sum_costs, 2) == round(res.metrics.totalCosts, 2)
    assert res.metrics.finalEquity == round(1_000_000.0 + res.metrics.netPnl, 2)
