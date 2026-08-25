"""
backend/app/research/metrics.py

Quantitative Performance and Risk Metrics for AURA Backtest Engine.
Calculates:
- Net & Gross P&L, Transaction Costs
- Annualized Sharpe & Sortino Ratios (with Indian risk-free rate adjustment)
- Maximum Drawdown (MDD) and Drawdown Duration
- Profit Factor, Win Rate, Expectancy, and Average R-Multiple
"""

from __future__ import annotations

import math
from typing import Optional
from pydantic import BaseModel


class EquityPoint(BaseModel):
    t: int
    equity: float
    drawdownPct: float


class BacktestMetrics(BaseModel):
    initialCapital: float
    finalEquity: float
    netPnl: float
    netPnlPct: float
    grossPnl: float
    totalCosts: float

    totalTrades: int
    winningTrades: int
    losingTrades: int
    winRate: float

    profitFactor: float
    sharpeRatio: float
    sortinoRatio: float
    maxDrawdownPct: float
    maxDrawdownDurationBars: int

    avgWin: float
    avgLoss: float
    avgRMultiple: float
    expectancy: float
    equityCurve: list[EquityPoint] = []


def calculate_metrics(
    initial_capital: float,
    trades: list[dict],
    equity_curve: list[tuple[int, float]],
    annual_risk_free_rate: float = 0.065,  # 6.5% Indian benchmark
    bars_per_year: int = 252,
) -> BacktestMetrics:
    """Calculate institutional performance metrics from trade logs and equity curve."""
    if not equity_curve:
        equity_curve = [(0, initial_capital)]

    final_equity = equity_curve[-1][1]
    net_pnl = final_equity - initial_capital
    net_pnl_pct = (net_pnl / initial_capital) if initial_capital > 0 else 0.0

    total_costs = sum(t.get("total_costs", 0.0) for t in trades)
    gross_pnl = sum(t.get("gross_pnl", 0.0) for t in trades)

    winning = [t for t in trades if t.get("net_pnl", 0.0) > 0]
    losing = [t for t in trades if t.get("net_pnl", 0.0) < 0]

    win_count = len(winning)
    loss_count = len(losing)
    total_trades = len(trades)
    win_rate = (win_count / total_trades) if total_trades > 0 else 0.0

    gross_gains = sum(t["net_pnl"] for t in winning)
    gross_losses = abs(sum(t["net_pnl"] for t in losing))
    profit_factor = (gross_gains / gross_losses) if gross_losses > 0 else (99.0 if gross_gains > 0 else 0.0)

    avg_win = (gross_gains / win_count) if win_count > 0 else 0.0
    avg_loss = (gross_losses / loss_count) if loss_count > 0 else 0.0
    expectancy = (win_rate * avg_win) - ((1.0 - win_rate) * avg_loss)

    r_multiples = [t.get("r_multiple", 0.0) for t in trades]
    avg_r = (sum(r_multiples) / len(r_multiples)) if r_multiples else 0.0

    # Drawdown calculation
    peak = initial_capital
    max_dd = 0.0
    current_dd_bars = 0
    max_dd_bars = 0
    equity_points: list[EquityPoint] = []

    for ts, eq in equity_curve:
        if eq > peak:
            peak = eq
            current_dd_bars = 0
        else:
            current_dd_bars += 1
            if current_dd_bars > max_dd_bars:
                max_dd_bars = current_dd_bars

        dd_pct = (peak - eq) / peak if peak > 0 else 0.0
        if dd_pct > max_dd:
            max_dd = dd_pct
        equity_points.append(EquityPoint(t=ts, equity=round(eq, 2), drawdownPct=round(dd_pct, 4)))

    # Sharpe & Sortino (Daily returns)
    returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev_eq = equity_curve[i - 1][1]
        curr_eq = equity_curve[i][1]
        if prev_eq > 0:
            returns.append((curr_eq - prev_eq) / prev_eq)

    rf_per_bar = annual_risk_free_rate / bars_per_year
    if len(returns) > 1:
        excess_returns = [r - rf_per_bar for r in returns]
        mean_excess = sum(excess_returns) / len(excess_returns)
        stdev = math.sqrt(sum((r - (sum(returns) / len(returns))) ** 2 for r in returns) / (len(returns) - 1))

        downside_returns = [min(0.0, r) for r in returns]
        downside_stdev = math.sqrt(sum(r ** 2 for r in downside_returns) / len(downside_returns)) if downside_returns else 0.0

        sharpe = (mean_excess / stdev * math.sqrt(bars_per_year)) if stdev > 0 else 0.0
        sortino = (mean_excess / downside_stdev * math.sqrt(bars_per_year)) if downside_stdev > 0 else 0.0
    else:
        sharpe = 0.0
        sortino = 0.0

    return BacktestMetrics(
        initialCapital=initial_capital,
        finalEquity=round(final_equity, 2),
        netPnl=round(net_pnl, 2),
        netPnlPct=round(net_pnl_pct, 4),
        grossPnl=round(gross_pnl, 2),
        totalCosts=round(total_costs, 2),
        totalTrades=total_trades,
        winningTrades=win_count,
        losingTrades=loss_count,
        winRate=round(win_rate, 4),
        profitFactor=round(min(99.0, profit_factor), 2),
        sharpeRatio=round(sharpe, 2),
        sortinoRatio=round(sortino, 2),
        maxDrawdownPct=round(max_dd, 4),
        maxDrawdownDurationBars=max_dd_bars,
        avgWin=round(avg_win, 2),
        avgLoss=round(avg_loss, 2),
        avgRMultiple=round(avg_r, 2),
        expectancy=round(expectancy, 2),
        equityCurve=equity_points,
    )
