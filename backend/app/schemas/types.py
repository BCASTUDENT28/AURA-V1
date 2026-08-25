"""
Pydantic schema mirrors of src/lib/aura/types.ts
Keep field names/shapes as close to TypeScript originals as practical.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Constants (mirrors of types.ts exports)
# ---------------------------------------------------------------------------

FEATURE_VERSION = "feat-v1"
DATASET_VERSION = "sim-in-eq-20240821"
MODEL_VERSION = "regime-rules-v1"
COST_VERSION = "in-cash-2026-unverified-v1"
STARTING_CASH = 1_000_000.0

# ---------------------------------------------------------------------------
# Enums / Literals
# ---------------------------------------------------------------------------

Action = Literal["BUY", "SELL", "HOLD", "SKIP"]
InstrumentKind = Literal["index", "equity"]
OrderSide = Literal["BUY", "SELL"]
OrderStatus = Literal["PENDING", "OPEN", "FILLED", "REJECTED", "CANCELLED"]
ProductType = Literal["INTRADAY", "DELIVERY"]

RegimeLabel = Literal[
    "BULL_TREND",
    "BEAR_TREND",
    "RANGE",
    "HIGH_VOL",
    "LOW_VOL",
    "BREAKOUT",
    "MEAN_REVERT",
    "STRESS",
]

# ---------------------------------------------------------------------------
# Market data models
# ---------------------------------------------------------------------------


class Bar(BaseModel):
    t: int          # timestamp ms
    o: float
    h: float
    l: float
    c: float
    v: float


class Quote(BaseModel):
    symbol: str
    ltp: float
    bid: float = 0.0
    ask: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    prevClose: float = 0.0
    change: float = 0.0
    changePct: float = 0.0
    volume: float = 0.0
    ts: int = 0


class Instrument(BaseModel):
    symbol: str
    name: str
    sector: str
    kind: InstrumentKind
    base: float
    tick: float
    lot: int
    avgVolume: float


# ---------------------------------------------------------------------------
# Indicator model (internal use)
# ---------------------------------------------------------------------------


class Indicators(BaseModel):
    smaFast: float
    smaSlow: float
    ema9: float
    ema21: float
    rsi: float
    macd: float
    macdSignal: float
    atr: float
    adx: float
    plusDi: float
    minusDi: float
    vwap: float
    bbUpper: float
    bbLower: float
    bbMid: float
    realizedVol: float
    volumeZ: float
    relVolume: float


# ---------------------------------------------------------------------------
# Regime
# ---------------------------------------------------------------------------


class Regime(BaseModel):
    label: RegimeLabel
    adx: float
    realizedVol: float
    volPercentile: float
    trendStrength: float
    notes: str


# ---------------------------------------------------------------------------
# Strategy output
# ---------------------------------------------------------------------------


class StrategyOutput(BaseModel):
    strategyId: str
    version: str
    action: Action
    entry: Optional[float]
    stop: Optional[float]
    target: Optional[float]
    confidence: float
    reason: str
    invalidation: str
    metadata: dict


# ---------------------------------------------------------------------------
# Similarity / Evidence
# ---------------------------------------------------------------------------


class SimilarMatch(BaseModel):
    n: int
    winRate: float
    avgReturn: float
    avgMae: float
    avgMfe: float
    avgHoldBars: int


class Evidence(BaseModel):
    text: str
    kind: Literal["support", "contradict", "neutral"]


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


class DecisionLineage(BaseModel):
    strategyVersion: str
    modelVersion: str
    featureVersion: str
    datasetVersion: str
    costVersion: str


class Decision(BaseModel):
    id: str
    symbol: str
    ts: int
    action: Action
    probabilityUp: float
    probabilityDown: float
    probabilityNeutral: float
    confidence: float
    risk: Literal["LOW", "MODERATE", "HIGH", "BLOCKED"]
    expectedRR: Optional[float]
    entry: Optional[float]
    stop: Optional[float]
    target: Optional[float]
    invalidation: str
    reasons: list[Evidence]
    contradictions: list[Evidence]
    strategy: StrategyOutput
    regime: Regime
    similar: SimilarMatch
    riskReasons: list[str]
    lineage: DecisionLineage


# ---------------------------------------------------------------------------
# Cost breakdown
# ---------------------------------------------------------------------------


class CostBreakdown(BaseModel):
    brokerage: float
    stt: float
    stamp: float
    exchange: float
    sebi: float
    gst: float
    slippage: float
    total: float


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------


class RiskLimits(BaseModel):
    maxPositionPct: float = 0.1
    maxDailyLossPct: float = 0.02
    maxExposurePct: float = 0.8
    maxPositions: int = 5
    maxSectorPct: float = 0.35
    opsPerSec: int = 9
    stopRequired: bool = True
    limitOnly: bool = True
    dataFreshMs: int = 5000


class RiskSnapshot(BaseModel):
    killSwitch: bool
    dailyPnl: float
    dailyPnlPct: float
    exposurePct: float
    openPositions: int
    dataAgeMs: int
    opsWindow: list[int]
    staticIpOk: bool
    env: str  # "PAPER" | "LIVE" | "DEV"
    livePathSealed: bool
    dataSource: str
    breaches: list[str]
    canTrade: bool


# ---------------------------------------------------------------------------
# Paper trading
# ---------------------------------------------------------------------------


class PaperPosition(BaseModel):
    symbol: str
    qty: float
    avgPrice: float
    side: OrderSide
    stop: Optional[float] = None
    target: Optional[float] = None
    openedTs: int = 0
    realized: float = 0.0
    costs: float = 0.0
    strategyId: Optional[str] = None


class PaperOrder(BaseModel):
    id: str
    ts: int
    symbol: str
    side: OrderSide
    type: Literal["LIMIT"]
    qty: float
    limitPrice: float
    status: OrderStatus = "OPEN"
    fillPrice: Optional[float] = None
    costs: Optional[CostBreakdown] = None
    rejectReason: Optional[str] = None
    strategyId: Optional[str] = None
    stop: Optional[float] = None
    target: Optional[float] = None


class PaperFill(BaseModel):
    id: str
    orderId: str
    ts: int
    symbol: str
    side: OrderSide
    qty: float
    price: float
    costs: CostBreakdown


class PaperBook(BaseModel):
    cash: float = STARTING_CASH
    realized: float = 0.0
    dailyPnl: float = 0.0
    sessionStartNav: float = STARTING_CASH
    killSwitch: bool = False
    orders: list[PaperOrder] = []
    positions: list[PaperPosition] = []
    fills: list[PaperFill] = []


# ---------------------------------------------------------------------------
# Learnings / Memory
# ---------------------------------------------------------------------------


class Learning(BaseModel):
    id: str
    ts: int
    kind: Literal["SUCCESS", "FAILURE", "REGIME", "RISK", "EXECUTION"]
    setup: str
    strategyId: str
    strategyVersion: str
    modelVersionId: Optional[str] = None
    featureVersionId: Optional[str] = None
    datasetVersionId: Optional[str] = None
    minSampleRequired: Optional[int] = None
    regime: RegimeLabel
    symbol: str
    evidence: str
    sampleSize: int
    confidence: float
    expiresTs: int
    rMultiple: Optional[float]
