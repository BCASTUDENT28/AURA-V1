"""
backend/app/research/walk_forward.py

Walk-Forward Optimization (WFO) Engine for AURA AI.
Evaluates strategy robustness across rolling In-Sample (Train) and Out-of-Sample (Test) windows.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from backend.app.quant.base_strategy import BaseStrategy, get_strategy
from backend.app.research.backtester import BacktestResult, CausalBacktester
from backend.app.research.metrics import BacktestMetrics, calculate_metrics
from backend.app.schemas.types import Bar


class WalkForwardWindow(BaseModel):
    windowNum: int
    trainStartMs: int
    trainEndMs: int
    testStartMs: int
    testEndMs: int
    bestParams: dict[str, Any]
    inSampleSharpe: float
    outOfSampleNetPnl: float
    outOfSampleTrades: int


class WalkForwardResult(BaseModel):
    strategyId: str
    symbol: str
    totalWindows: int
    windows: list[WalkForwardWindow] = []
    combinedOutOfSampleMetrics: BacktestMetrics


class WalkForwardOptimizer:
    """Rolling walk-forward evaluation harness."""

    def __init__(
        self,
        strategy_id: str,
        param_grid: list[dict[str, Any]],
        train_bars: int = 150,
        test_bars: int = 40,
        step_bars: int = 40,
    ):
        self.strategy_id = strategy_id
        self.param_grid = param_grid
        self.train_bars = train_bars
        self.test_bars = test_bars
        self.step_bars = step_bars

    def run(self, symbol: str, bars: list[Bar]) -> WalkForwardResult:
        total_len = len(bars)
        min_required = self.train_bars + self.test_bars
        if total_len < min_required:
            raise ValueError(f"Need at least {min_required} bars for walk-forward; got {total_len}.")

        windows: list[WalkForwardWindow] = []
        all_oos_trades: list[dict] = []
        all_oos_equity: list[tuple[int, float]] = []

        curr_capital = 1_000_000.0
        start_idx = 0
        window_idx = 0

        while start_idx + self.train_bars + self.test_bars <= total_len:
            window_idx += 1
            train_slice = bars[start_idx : start_idx + self.train_bars]
            test_slice = bars[start_idx + self.train_bars : start_idx + self.train_bars + self.test_bars]

            # 1. Optimize on In-Sample (Train)
            best_score = -999.0
            best_params = self.param_grid[0] if self.param_grid else {}

            for p in self.param_grid:
                strat = get_strategy(self.strategy_id, params=p)
                bt = CausalBacktester(strategy=strat, initial_capital=curr_capital)
                res = bt.run(symbol, train_slice, min_warmup_bars=25)
                score = res.metrics.sharpeRatio

                if score > best_score:
                    best_score = score
                    best_params = p

            # 2. Evaluate Best Params on Out-of-Sample (Test)
            best_strat = get_strategy(self.strategy_id, params=best_params)
            oos_bt = CausalBacktester(strategy=best_strat, initial_capital=curr_capital)
            oos_res = oos_bt.run(symbol, test_slice, min_warmup_bars=15)

            curr_capital = oos_res.metrics.finalEquity

            windows.append(
                WalkForwardWindow(
                    windowNum=window_idx,
                    trainStartMs=train_slice[0].t,
                    trainEndMs=train_slice[-1].t,
                    testStartMs=test_slice[0].t,
                    testEndMs=test_slice[-1].t,
                    bestParams=best_params,
                    inSampleSharpe=round(best_score, 2),
                    outOfSampleNetPnl=round(oos_res.metrics.netPnl, 2),
                    outOfSampleTrades=oos_res.metrics.totalTrades,
                )
            )

            for t in oos_res.trades:
                all_oos_trades.append(t.model_dump())
            for eq_pt in oos_res.metrics.equityCurve:
                all_oos_equity.append((eq_pt.t, eq_pt.equity))

            start_idx += self.step_bars

        combined_metrics = calculate_metrics(
            initial_capital=1_000_000.0,
            trades=all_oos_trades,
            equity_curve=all_oos_equity,
        )

        return WalkForwardResult(
            strategyId=self.strategy_id,
            symbol=symbol,
            totalWindows=len(windows),
            windows=windows,
            combinedOutOfSampleMetrics=combined_metrics,
        )
