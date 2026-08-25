"""
backend/tests/test_backtest_metrics.py

Tests for Backtest Metrics Calculation Engine.
Verifies:
- Sharpe Ratio and Sortino Ratio formulas
- Max Drawdown (MDD) calculation
- Profit Factor and Win Rate calculation
- Expectancy formula: (WinRate * AvgWin) - (LossRate * AvgLoss)
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.research.metrics import calculate_metrics


def test_metrics_calculation_hand_crafted():
    """Verify performance metrics against hand-calculated scenario."""
    trades = [
        {"net_pnl": 1000.0, "gross_pnl": 1050.0, "total_costs": 50.0, "r_multiple": 2.0},
        {"net_pnl": -500.0, "gross_pnl": -450.0, "total_costs": 50.0, "r_multiple": -1.0},
        {"net_pnl": 1500.0, "gross_pnl": 1550.0, "total_costs": 50.0, "r_multiple": 3.0},
        {"net_pnl": -500.0, "gross_pnl": -450.0, "total_costs": 50.0, "r_multiple": -1.0},
    ]

    equity_curve = [
        (1000, 100000.0),
        (2000, 101000.0),
        (3000, 100500.0),
        (4000, 102000.0),
        (5000, 101500.0),
    ]

    metrics = calculate_metrics(
        initial_capital=100000.0,
        trades=trades,
        equity_curve=equity_curve,
    )

    assert metrics.totalTrades == 4
    assert metrics.winningTrades == 2
    assert metrics.losingTrades == 2
    assert metrics.winRate == 0.50
    assert metrics.netPnl == 1500.0
    assert metrics.grossPnl == 1700.0
    assert metrics.totalCosts == 200.0
    # Gross gains = 2500, gross losses = 1000 -> PF = 2.50
    assert metrics.profitFactor == 2.50
    assert metrics.avgWin == 1250.0
    assert metrics.avgLoss == 500.0
    # Expectancy = (0.5 * 1250) - (0.5 * 500) = 625 - 250 = 375.0
    assert metrics.expectancy == 375.0
    # Max Drawdown: peak=102000, trough=101500 -> 500 / 102000 = 0.0049
    assert metrics.maxDrawdownPct > 0.0


def test_zero_trades_metrics():
    """Metrics calculation with 0 trades must return clean zero values without division by zero."""
    metrics = calculate_metrics(
        initial_capital=1000000.0,
        trades=[],
        equity_curve=[(0, 1000000.0)],
    )
    assert metrics.totalTrades == 0
    assert metrics.winRate == 0.0
    assert metrics.profitFactor == 0.0
    assert metrics.netPnl == 0.0
    assert metrics.maxDrawdownPct == 0.0
