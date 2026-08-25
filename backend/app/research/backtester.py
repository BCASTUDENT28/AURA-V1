"""
backend/app/research/backtester.py

Event-Driven Causal Backtesting Engine for AURA AI.
Enforces:
- Strict next-bar fill modeling (signal generated at close(t) fills at open(t+1) or matches high/low(t+1)).
- Authoritative Indian discount-broker cost deductions on every entry and exit fill.
- Intrabar stop-loss and take-profit execution.
- Multi-symbol portfolio aggregation and equity curve generation.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional
from pydantic import BaseModel, Field

from backend.app.engines.cost.cost import estimate_costs
from backend.app.quant.base_strategy import BaseStrategy, get_strategy
from backend.app.quant.features import extract_features
from backend.app.research.metrics import BacktestMetrics, calculate_metrics
from backend.app.schemas.types import Bar, OrderSide, ProductType


class BacktestTradeRecord(BaseModel):
    tradeNum: int
    symbol: str
    side: OrderSide
    qty: float
    entryTs: int
    entryPx: float
    exitTs: int
    exitPx: float
    grossPnl: float
    netPnl: float
    totalCosts: float
    rMultiple: float
    exitReason: str                    # 'STOP_LOSS' | 'TAKE_PROFIT' | 'SIGNAL' | 'SESSION_CLOSE'
    durationBars: int


class BacktestResult(BaseModel):
    runId: str
    strategyId: str
    symbol: str
    timeframe: str
    params: dict[str, Any] = Field(default_factory=dict)
    metrics: BacktestMetrics
    trades: list[BacktestTradeRecord] = []


class CausalBacktester:
    """Deterministic event-driven backtesting engine."""

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: float = 1_000_000.0,
        max_position_pct: float = 0.10,   # Max 10% capital per position
        product: ProductType = "INTRADAY",
    ):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.max_position_pct = max_position_pct
        self.product = product

    def run(
        self,
        symbol: str,
        bars: list[Bar],
        timeframe: str = "1D",
        min_warmup_bars: int = 35,
    ) -> BacktestResult:
        if len(bars) < min_warmup_bars + 5:
            raise ValueError(f"Insufficient bars ({len(bars)}) for backtesting. Need at least {min_warmup_bars + 5}.")

        cash = self.initial_capital
        equity = cash
        equity_curve: list[tuple[int, float]] = [(bars[0].t, cash)]
        trades: list[dict] = []
        trade_records: list[BacktestTradeRecord] = []

        active_pos: Optional[dict] = None
        pending_signal: Optional[dict] = None
        trade_counter = 0

        for i in range(min_warmup_bars, len(bars)):
            curr_bar = bars[i]
            prev_bar = bars[i - 1]

            # -------------------------------------------------------------
            # 1. Process Pending Entry Order from Previous Bar (Causal Fill)
            # -------------------------------------------------------------
            if pending_signal and not active_pos:
                sig = pending_signal
                entry_px = curr_bar.o  # Next-bar open fill
                max_pos_val = equity * self.max_position_pct
                qty = math_floor = max(1, int(max_pos_val / entry_px))

                # Entry costs
                entry_turnover = qty * entry_px
                entry_costs = estimate_costs(
                    turnover=entry_turnover,
                    side=sig["action"],
                    product=self.product,
                    kind="equity",
                )

                cash -= entry_costs.total
                active_pos = {
                    "symbol": symbol,
                    "side": sig["action"],
                    "qty": qty,
                    "entry_ts": curr_bar.t,
                    "entry_px": entry_px,
                    "stop": sig.get("stop"),
                    "target": sig.get("target"),
                    "entry_costs": entry_costs.total,
                    "entry_bar_idx": i,
                }
                pending_signal = None

            # -------------------------------------------------------------
            # 2. Check Active Position Exits (Stop-Loss / Target / Intrabar)
            # -------------------------------------------------------------
            if active_pos:
                pos = active_pos
                side = pos["side"]
                stop = pos["stop"]
                target = pos["target"]
                exit_px: Optional[float] = None
                exit_reason = "SIGNAL"

                if side == "BUY":
                    if stop and curr_bar.l <= stop:
                        exit_px = stop
                        exit_reason = "STOP_LOSS"
                    elif target and curr_bar.h >= target:
                        exit_px = target
                        exit_reason = "TAKE_PROFIT"
                elif side == "SELL":
                    if stop and curr_bar.h >= stop:
                        exit_px = stop
                        exit_reason = "STOP_LOSS"
                    elif target and curr_bar.l <= target:
                        exit_px = target
                        exit_reason = "TAKE_PROFIT"

                # If last bar of series, force session close
                if exit_px is None and i == len(bars) - 1:
                    exit_px = curr_bar.c
                    exit_reason = "SESSION_CLOSE"

                if exit_px is not None:
                    trade_counter += 1
                    exit_turnover = pos["qty"] * exit_px
                    exit_costs = estimate_costs(
                        turnover=exit_turnover,
                        side="SELL" if side == "BUY" else "BUY",
                        product=self.product,
                        kind="equity",
                    )

                    total_trade_costs = pos["entry_costs"] + exit_costs.total
                    dir_mult = 1.0 if side == "BUY" else -1.0
                    gross_pnl = dir_mult * (exit_px - pos["entry_px"]) * pos["qty"]
                    net_pnl = gross_pnl - total_trade_costs

                    cash += net_pnl
                    initial_risk = abs(pos["entry_px"] - (pos["stop"] or (pos["entry_px"] * 0.99))) * pos["qty"]
                    r_mult = (gross_pnl / initial_risk) if initial_risk > 0 else 0.0

                    trade_data = {
                        "trade_num": trade_counter,
                        "symbol": symbol,
                        "side": side,
                        "qty": pos["qty"],
                        "entry_ts": pos["entry_ts"],
                        "entry_px": round(pos["entry_px"], 2),
                        "exit_ts": curr_bar.t,
                        "exit_px": round(exit_px, 2),
                        "gross_pnl": round(gross_pnl, 2),
                        "net_pnl": round(net_pnl, 2),
                        "total_costs": round(total_trade_costs, 2),
                        "r_multiple": round(r_mult, 2),
                        "exit_reason": exit_reason,
                        "duration_bars": i - pos["entry_bar_idx"],
                    }
                    trades.append(trade_data)
                    trade_records.append(BacktestTradeRecord(**{
                        "tradeNum": trade_data["trade_num"],
                        "symbol": trade_data["symbol"],
                        "side": trade_data["side"],
                        "qty": trade_data["qty"],
                        "entryTs": trade_data["entry_ts"],
                        "entryPx": trade_data["entry_px"],
                        "exitTs": trade_data["exit_ts"],
                        "exitPx": trade_data["exit_px"],
                        "grossPnl": trade_data["gross_pnl"],
                        "netPnl": trade_data["net_pnl"],
                        "totalCosts": trade_data["total_costs"],
                        "rMultiple": trade_data["r_multiple"],
                        "exitReason": trade_data["exit_reason"],
                        "durationBars": trade_data["duration_bars"],
                    }))
                    active_pos = None

            # -------------------------------------------------------------
            # 3. Mark-to-Market Equity Calculation
            # -------------------------------------------------------------
            unrealized = 0.0
            if active_pos:
                dir_mult = 1.0 if active_pos["side"] == "BUY" else -1.0
                unrealized = dir_mult * (curr_bar.c - active_pos["entry_px"]) * active_pos["qty"]

            equity = cash + unrealized
            equity_curve.append((curr_bar.t, equity))

            # -------------------------------------------------------------
            # 4. Generate Signal at Bar Close (strictly historical slice [:i+1])
            # -------------------------------------------------------------
            if not active_pos and not pending_signal:
                hist_slice = bars[:i + 1]
                feat = extract_features(hist_slice)
                sig = self.strategy.evaluate(hist_slice, features=feat)
                if sig.action in ("BUY", "SELL") and sig.confidence >= 0.50:
                    pending_signal = {
                        "action": sig.action,
                        "stop": sig.stop,
                        "target": sig.target,
                        "confidence": sig.confidence,
                    }

        metrics = calculate_metrics(
            initial_capital=self.initial_capital,
            trades=trades,
            equity_curve=equity_curve,
        )

        run_id = f"run-{self.strategy.id}-{symbol}-{timeframe}-{uuid.uuid4().hex[:8]}"
        return BacktestResult(
            runId=run_id,
            strategyId=self.strategy.id,
            symbol=symbol,
            timeframe=timeframe,
            params=self.strategy.params,
            metrics=metrics,
            trades=trade_records,
        )
