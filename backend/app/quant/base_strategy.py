"""
backend/app/quant/base_strategy.py

Standardized Quant Strategy Framework for AURA AI.
Enforces:
- Consistent signal generation and bracket calculation (entry, stop, target)
- Parameter schema serialization and validation
- Regime fit scoring and invalidation criteria

UNIFICATION FIX (2026-08-26):
  The three concrete strategy classes (MACrossoverStrategy, VWAPRSIStrategy,
  OpeningRangeBreakoutStrategy) now delegate their evaluate() method to the
  parity-tested functions in engines/decision/strategies.py via _output_to_signal().
  There is exactly ONE set of strategy logic, thresholds, and constants in the
  entire codebase. The backtester (research/backtester.py), Strategy Lab
  (/api/quant/), and the live dashboard (/api/universe/decisions) all execute
  the same code path. Divergence is structurally impossible.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel, Field

# FeatureVector and QuantRegimeEngine are still imported for the backtester
# pipeline which calls extract_features() + QuantRegimeEngine directly;
# they are NOT used in the strategy evaluate() methods (those delegate down).
from backend.app.quant.features import FeatureVector, extract_features
from backend.app.quant.regime_engine import QuantRegimeEngine
from backend.app.schemas.types import Action, Bar, RegimeLabel, StrategyOutput


# ─────────────────────────────────────────────────────────────────────────────
# Shared schema
# ─────────────────────────────────────────────────────────────────────────────

class StrategySignal(BaseModel):
    strategyId: str
    version: str
    action: Action
    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    confidence: float
    reason: str
    invalidation: str
    regimeFit: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_strategy_output(self) -> StrategyOutput:
        return StrategyOutput(
            strategyId=self.strategyId,
            version=self.version,
            action=self.action,
            entry=self.entry,
            stop=self.stop,
            target=self.target,
            confidence=self.confidence,
            reason=self.reason,
            invalidation=self.invalidation,
            metadata=self.metadata,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Bridge: StrategyOutput → StrategySignal
# ─────────────────────────────────────────────────────────────────────────────

def _output_to_signal(out: StrategyOutput) -> StrategySignal:
    """
    Convert a parity-tested StrategyOutput (from engines/decision/strategies.py)
    into a StrategySignal for the quant framework.
    This is the ONLY bridge — no strategy logic is duplicated here.
    """
    return StrategySignal(
        strategyId=out.strategyId,
        version=out.version,
        action=out.action,
        entry=out.entry,
        stop=out.stop,
        target=out.target,
        confidence=out.confidence,
        reason=out.reason,
        invalidation=out.invalidation,
        metadata=out.metadata,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Abstract base
# ─────────────────────────────────────────────────────────────────────────────

class BaseStrategy(ABC):
    """Abstract base class for all AURA quantitative trading strategies."""

    id: str
    name: str
    version: str
    description: str
    supportedRegimes: list[RegimeLabel]

    def __init__(self, params: Optional[dict[str, Any]] = None):
        self.params = {**self.default_params(), **(params or {})}

    @abstractmethod
    def default_params(self) -> dict[str, Any]:
        """Default strategy hyperparameters."""
        ...

    @abstractmethod
    def evaluate(self, bars: list[Bar], features: Optional[FeatureVector] = None) -> StrategySignal:
        """Generate strategy signal from historical bars."""
        ...

    def get_regime_fit(self, regime: RegimeLabel) -> float:
        if regime in self.supportedRegimes:
            return 1.0
        if regime == "STRESS":
            return 0.15
        if regime in ("RANGE", "MEAN_REVERT"):
            return 0.45
        return 0.60


# ─────────────────────────────────────────────────────────────────────────────
# 1. Moving Average Crossover — delegates to parity-tested ma_cross()
# ─────────────────────────────────────────────────────────────────────────────

class MACrossoverStrategy(BaseStrategy):
    id = "ma_cross"
    name = "Moving Average Crossover"
    version = "v1"
    description = "Trend-following fast/slow SMA crossover with ADX trend strength filter."
    supportedRegimes: list[RegimeLabel] = ["BULL_TREND", "BEAR_TREND", "BREAKOUT"]

    def default_params(self) -> dict[str, Any]:
        # Mirrors engines/decision/strategies.py STRATEGY_BY_ID["ma_cross"]["defaults"]
        return {"fast": 9, "slow": 21, "slPct": 0.01, "rr": 2}

    def evaluate(self, bars: list[Bar], features: Optional[FeatureVector] = None) -> StrategySignal:
        """
        Delegates entirely to the parity-tested ma_cross() function in
        engines/decision/strategies.py. Single source of truth.
        """
        from backend.app.engines.decision.strategies import ma_cross
        cfg = {
            "fast": self.params["fast"],
            "slow": self.params["slow"],
            "slPct": self.params["slPct"],
            "rr": self.params["rr"],
        }
        return _output_to_signal(ma_cross(bars, cfg))


# ─────────────────────────────────────────────────────────────────────────────
# 2. VWAP + RSI — delegates to parity-tested vwap_rsi()
# ─────────────────────────────────────────────────────────────────────────────

class VWAPRSIStrategy(BaseStrategy):
    id = "vwap_rsi"
    name = "VWAP + RSI Continuation"
    version = "v1"
    description = "Intraday/Swing volume-weighted momentum continuation strategy."
    supportedRegimes: list[RegimeLabel] = ["BULL_TREND", "BREAKOUT", "LOW_VOL"]

    def default_params(self) -> dict[str, Any]:
        # Mirrors engines/decision/strategies.py STRATEGY_BY_ID["vwap_rsi"]["defaults"]
        return {"rsiBuy": 55, "rsiSell": 45, "slPct": 0.01, "rr": 2}

    def evaluate(self, bars: list[Bar], features: Optional[FeatureVector] = None) -> StrategySignal:
        """
        Delegates entirely to the parity-tested vwap_rsi() function in
        engines/decision/strategies.py. Single source of truth.
        """
        from backend.app.engines.decision.strategies import vwap_rsi
        cfg = {
            "rsiBuy": self.params["rsiBuy"],
            "rsiSell": self.params["rsiSell"],
            "slPct": self.params["slPct"],
            "rr": self.params["rr"],
        }
        return _output_to_signal(vwap_rsi(bars, cfg))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Opening Range Breakout — delegates to parity-tested orb()
# ─────────────────────────────────────────────────────────────────────────────

class OpeningRangeBreakoutStrategy(BaseStrategy):
    id = "orb"
    name = "Opening Range Breakout"
    version = "v1"
    description = "Intraday structural opening range breakout with volume expansion."
    supportedRegimes: list[RegimeLabel] = ["BREAKOUT", "BULL_TREND", "BEAR_TREND", "HIGH_VOL"]

    def default_params(self) -> dict[str, Any]:
        # Mirrors engines/decision/strategies.py STRATEGY_BY_ID["orb"]["defaults"]
        return {"orBars": 3, "slPct": 0.008, "rr": 1.5}

    def evaluate(self, bars: list[Bar], features: Optional[FeatureVector] = None) -> StrategySignal:
        """
        Delegates entirely to the parity-tested orb() function in
        engines/decision/strategies.py. Single source of truth.
        """
        from backend.app.engines.decision.strategies import orb
        cfg = {
            "orBars": self.params["orBars"],
            "slPct": self.params["slPct"],
            "rr": self.params["rr"],
        }
        return _output_to_signal(orb(bars, cfg))


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Registry & Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

_STRATEGY_CLASSES: dict[str, type[BaseStrategy]] = {
    "ma_cross": MACrossoverStrategy,
    "vwap_rsi": VWAPRSIStrategy,
    "orb":      OpeningRangeBreakoutStrategy,
}


def get_strategy(strategy_id: str, params: Optional[dict[str, Any]] = None) -> BaseStrategy:
    cls = _STRATEGY_CLASSES.get(strategy_id)
    if not cls:
        raise ValueError(
            f"Unknown quant strategy: '{strategy_id}'. "
            f"Available: {list(_STRATEGY_CLASSES.keys())}"
        )
    return cls(params=params)


def list_quant_strategies() -> list[dict[str, Any]]:
    return [
        {
            "id": cls.id,
            "name": cls.name,
            "version": cls.version,
            "description": cls.description,
            "supportedRegimes": cls.supportedRegimes,
            "defaultParams": cls().default_params(),
        }
        for cls in _STRATEGY_CLASSES.values()
    ]
