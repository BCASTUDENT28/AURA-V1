"""
backend/app/quant/base_strategy.py

Standardized Quant Strategy Framework for AURA AI.
Enforces:
- Consistent signal generation and bracket calculation (entry, stop, target)
- Parameter schema serialization and validation
- Regime fit scoring and invalidation criteria
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel, Field

from backend.app.quant.features import FeatureVector, extract_features
from backend.app.quant.regime_engine import QuantRegimeEngine
from backend.app.schemas.types import Action, Bar, RegimeLabel, StrategyOutput


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
        """Generate strategy signal from historical bars and pre-computed features."""
        ...

    def get_regime_fit(self, regime: RegimeLabel) -> float:
        if regime in self.supportedRegimes:
            return 1.0
        if regime == "STRESS":
            return 0.15
        if regime in ("RANGE", "MEAN_REVERT"):
            return 0.45
        return 0.60


# ---------------------------------------------------------------------------
# 1. Moving Average Crossover Strategy
# ---------------------------------------------------------------------------

class MACrossoverStrategy(BaseStrategy):
    id = "ma_cross"
    name = "Moving Average Crossover"
    version = "v1"
    description = "Trend-following fast/slow SMA crossover with ADX trend strength filter."
    supportedRegimes: list[RegimeLabel] = ["BULL_TREND", "BEAR_TREND", "BREAKOUT"]

    def default_params(self) -> dict[str, Any]:
        return {
            "fast": 9,
            "slow": 21,
            "adxMin": 15.0,
            "slPct": 0.01,
            "rr": 2.0,
        }

    def evaluate(self, bars: list[Bar], features: Optional[FeatureVector] = None) -> StrategySignal:
        feat = features or extract_features(bars)
        prev_feat = extract_features(bars[:-1]) if len(bars) > 1 else feat
        px = feat.close
        sl_pct = self.params["slPct"]
        rr = self.params["rr"]
        adx_min = self.params["adxMin"]

        crossed_up = prev_feat.sma9 <= prev_feat.sma21 and feat.sma9 > feat.sma21
        crossed_dn = prev_feat.sma9 >= prev_feat.sma21 and feat.sma9 < feat.sma21
        aligned_up = feat.sma9 > feat.sma21 and feat.ema9 > feat.ema21
        aligned_dn = feat.sma9 < feat.sma21 and feat.ema9 < feat.ema21

        if feat.adx14 < adx_min:
            return StrategySignal(
                strategyId=self.id,
                version=self.version,
                action="SKIP",
                confidence=0.35,
                reason=f"ADX {feat.adx14:.1f} < {adx_min} — low directional momentum.",
                invalidation=f"Wait for ADX > {adx_min + 3:.0f}.",
                metadata={"adx": feat.adx14, "smaFast": feat.sma9, "smaSlow": feat.sma21},
            )

        if crossed_up or (aligned_up and 52 < feat.rsi14 < 72):
            stop = px * (1.0 - sl_pct)
            target = px + (px - stop) * rr
            conf = min(0.82, 0.50 + feat.adx14 / 80.0 + (0.10 if crossed_up else 0.0))
            return StrategySignal(
                strategyId=self.id,
                version=self.version,
                action="BUY",
                entry=px,
                stop=round(stop, 2),
                target=round(target, 2),
                confidence=round(conf, 4),
                reason="Fast SMA crossed/holding above slow SMA with confirmed ADX trend.",
                invalidation=f"Close back below SMA21 ({feat.sma21:.2f}) or stop at {stop:.2f}.",
                metadata={"rsi": feat.rsi14, "adx": feat.adx14, "sma9": feat.sma9, "sma21": feat.sma21},
            )

        if crossed_dn or (aligned_dn and 28 < feat.rsi14 < 48):
            stop = px * (1.0 + sl_pct)
            target = px - (stop - px) * rr
            conf = min(0.80, 0.50 + feat.adx14 / 80.0 + (0.10 if crossed_dn else 0.0))
            return StrategySignal(
                strategyId=self.id,
                version=self.version,
                action="SELL",
                entry=px,
                stop=round(stop, 2),
                target=round(target, 2),
                confidence=round(conf, 4),
                reason="Fast SMA crossed/holding below slow SMA with confirmed ADX downside.",
                invalidation=f"Close back above SMA21 ({feat.sma21:.2f}) or stop at {stop:.2f}.",
                metadata={"rsi": feat.rsi14, "adx": feat.adx14, "sma9": feat.sma9, "sma21": feat.sma21},
            )

        return StrategySignal(
            strategyId=self.id,
            version=self.version,
            action="HOLD",
            confidence=0.45,
            reason="No fresh crossover and RSI in mid-range band. Stand aside.",
            invalidation="A directional 9/21 cross with ADX confirmation.",
            metadata={"rsi": feat.rsi14, "adx": feat.adx14},
        )


# ---------------------------------------------------------------------------
# 2. VWAP + RSI Strategy
# ---------------------------------------------------------------------------

class VWAPRSIStrategy(BaseStrategy):
    id = "vwap_rsi"
    name = "VWAP + RSI Continuation"
    version = "v1"
    description = "Intraday/Swing volume-weighted momentum continuation strategy."
    supportedRegimes: list[RegimeLabel] = ["BULL_TREND", "BREAKOUT", "LOW_VOL"]

    def default_params(self) -> dict[str, Any]:
        return {
            "rsiBuy": 55.0,
            "rsiSell": 45.0,
            "minRelVolume": 1.10,
            "slPct": 0.01,
            "rr": 2.0,
        }

    def evaluate(self, bars: list[Bar], features: Optional[FeatureVector] = None) -> StrategySignal:
        feat = features or extract_features(bars)
        px = feat.close
        vwap = feat.vwap20
        rsi = feat.rsi14
        rv = feat.relVolume20
        sl_pct = self.params["slPct"]
        rr = self.params["rr"]

        above = px > vwap
        vol_ok = rv >= self.params["minRelVolume"]

        if above and self.params["rsiBuy"] <= rsi <= 72 and vol_ok:
            stop = min(px * (1.0 - sl_pct), vwap * 0.997)
            target = px + (px - stop) * rr
            conf = min(0.84, 0.48 + (rv - 1.0) * 0.15 + (rsi - 50) / 120.0)
            return StrategySignal(
                strategyId=self.id,
                version=self.version,
                action="BUY",
                entry=px,
                stop=round(stop, 2),
                target=round(target, 2),
                confidence=round(conf, 4),
                reason=f"Price {(px / vwap - 1) * 100:.2f}% above VWAP with RSI {rsi:.0f} and volume {rv:.2f}x.",
                invalidation=f"VWAP breakdown below {vwap:.2f} or RSI rollover.",
                metadata={"vwap": vwap, "rsi": rsi, "relVolume": rv},
            )

        if not above and rsi <= self.params["rsiSell"] and rsi >= 28 and vol_ok:
            stop = max(px * (1.0 + sl_pct), vwap * 1.003)
            target = px - (stop - px) * rr
            conf = min(0.82, 0.48 + (rv - 1.0) * 0.15 + (50 - rsi) / 120.0)
            return StrategySignal(
                strategyId=self.id,
                version=self.version,
                action="SELL",
                entry=px,
                stop=round(stop, 2),
                target=round(target, 2),
                confidence=round(conf, 4),
                reason=f"Price below VWAP with RSI {rsi:.0f} and volume confirmation {rv:.2f}x.",
                invalidation=f"VWAP reclaim above {vwap:.2f} or RSI reclaim of 50.",
                metadata={"vwap": vwap, "rsi": rsi, "relVolume": rv},
            )

        if not vol_ok:
            return StrategySignal(
                strategyId=self.id,
                version=self.version,
                action="SKIP",
                confidence=0.38,
                reason=f"Relative volume ({rv:.2f}x) is thin. VWAP breaks without volume are faded.",
                invalidation="Relative volume > 1.1x with directional VWAP hold.",
                metadata={"relVolume": rv, "rsi": rsi},
            )

        return StrategySignal(
            strategyId=self.id,
            version=self.version,
            action="HOLD",
            confidence=0.42,
            reason=f"RSI {rsi:.0f} outside active continuation band.",
            invalidation="RSI entry into continuation band relative to VWAP.",
            metadata={"rsi": rsi, "vwap": vwap},
        )


# ---------------------------------------------------------------------------
# 3. Opening Range Breakout (ORB)
# ---------------------------------------------------------------------------

class OpeningRangeBreakoutStrategy(BaseStrategy):
    id = "orb"
    name = "Opening Range Breakout"
    version = "v1"
    description = "Intraday structural opening range breakout with volume expansion."
    supportedRegimes: list[RegimeLabel] = ["BREAKOUT", "BULL_TREND", "BEAR_TREND", "HIGH_VOL"]

    def default_params(self) -> dict[str, Any]:
        return {
            "orBars": 3,
            "maxRangePct": 0.025,
            "slPct": 0.008,
            "rr": 1.5,
        }

    def evaluate(self, bars: list[Bar], features: Optional[FeatureVector] = None) -> StrategySignal:
        or_bars = int(self.params["orBars"])
        if len(bars) < or_bars + 5:
            return StrategySignal(
                strategyId=self.id,
                version=self.version,
                action="SKIP",
                confidence=0.20,
                reason="Insufficient bars to establish opening range structure.",
                invalidation="Wait for opening range establishment.",
            )

        opening = bars[-20:-20 + or_bars] if len(bars) >= 20 else bars[:or_bars]
        orh = max(b.h for b in opening)
        orl = min(b.l for b in opening)
        px = bars[-1].c
        feat = features or extract_features(bars)
        range_pct = (orh - orl) / ((orh + orl) / 2.0) if (orh + orl) > 0 else 0

        if range_pct > self.params["maxRangePct"]:
            return StrategySignal(
                strategyId=self.id,
                version=self.version,
                action="SKIP",
                confidence=0.33,
                reason=f"Opening range ({range_pct * 100:.2f}%) is too wide — breakout R:R is compromised.",
                invalidation="Opening range < 2.5%.",
                metadata={"orh": orh, "orl": orl, "rangePct": range_pct},
            )

        sl_pct = self.params["slPct"]
        rr = self.params["rr"]

        if px > orh and feat.relVolume20 > 1.05:
            stop = max(orl, px * (1.0 - sl_pct))
            target = px + (px - stop) * rr
            conf = min(0.80, 0.50 + feat.relVolume20 * 0.10)
            return StrategySignal(
                strategyId=self.id,
                version=self.version,
                action="BUY",
                entry=px,
                stop=round(stop, 2),
                target=round(target, 2),
                confidence=round(conf, 4),
                reason=f"Break of opening-range high ({orh:.2f}) with volume expansion ({feat.relVolume20:.2f}x).",
                invalidation=f"Re-entry inside range ({orh:.2f}) or stop at {stop:.2f}.",
                metadata={"orh": orh, "orl": orl, "relVolume": feat.relVolume20},
            )

        if px < orl and feat.relVolume20 > 1.05:
            stop = min(orh, px * (1.0 + sl_pct))
            target = px - (stop - px) * rr
            conf = min(0.78, 0.50 + feat.relVolume20 * 0.10)
            return StrategySignal(
                strategyId=self.id,
                version=self.version,
                action="SELL",
                entry=px,
                stop=round(stop, 2),
                target=round(target, 2),
                confidence=round(conf, 4),
                reason=f"Break of opening-range low ({orl:.2f}) with volume expansion.",
                invalidation=f"Re-entry inside range ({orl:.2f}) or stop at {stop:.2f}.",
                metadata={"orh": orh, "orl": orl, "relVolume": feat.relVolume20},
            )

        return StrategySignal(
            strategyId=self.id,
            version=self.version,
            action="HOLD",
            confidence=0.40,
            reason=f"Price consolidating inside opening range ({orl:.2f} - {orh:.2f}).",
            invalidation="Confirmed range breakout with volume.",
            metadata={"orh": orh, "orl": orl},
        )


# ---------------------------------------------------------------------------
# Strategy Registry & Dispatcher
# ---------------------------------------------------------------------------

_STRATEGY_CLASSES: dict[str, type[BaseStrategy]] = {
    "ma_cross": MACrossoverStrategy,
    "vwap_rsi": VWAPRSIStrategy,
    "orb": OpeningRangeBreakoutStrategy,
}


def get_strategy(strategy_id: str, params: Optional[dict[str, Any]] = None) -> BaseStrategy:
    cls = _STRATEGY_CLASSES.get(strategy_id)
    if not cls:
        raise ValueError(f"Unknown quant strategy: '{strategy_id}'. Available: {list(_STRATEGY_CLASSES.keys())}")
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
