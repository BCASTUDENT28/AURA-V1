"""
backend/app/schemas/market_data.py

Pydantic schemas for Phase 2:
- Canonical Instrument Master & Broker Mappings
- Corporate Actions
- Dataset Versions & Lineage
- Data Quality Audits & Historical OHLCV Queries
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Instrument & Broker Mappings
# ---------------------------------------------------------------------------

Exchange = Literal["NSE", "BSE"]
Segment = Literal["EQUITY", "INDEX", "FNO"]
BrokerName = Literal["ANGEL_ONE", "GROWW", "ZERODHA"]
Timeframe = Literal["1m", "3m", "5m", "15m", "1D"]


class BrokerMapping(BaseModel):
    broker: BrokerName
    brokerSymbol: str
    brokerToken: str
    segment: str = "NSE_CM"
    isValid: bool = True
    verifiedAt: Optional[str] = None


class InstrumentRecord(BaseModel):
    id: str                            # e.g. "NSE:RELIANCE"
    symbol: str                        # e.g. "RELIANCE"
    name: str
    exchange: Exchange = "NSE"
    segment: Segment = "EQUITY"
    sector: str = "General"
    kind: Literal["equity", "index"] = "equity"
    lotSize: int = 1
    tickSize: float = 0.05
    basePrice: float
    avgVolume: float = 1_000_000.0
    isActive: bool = True
    brokerMappings: list[BrokerMapping] = []


# ---------------------------------------------------------------------------
# Corporate Actions
# ---------------------------------------------------------------------------

CorporateActionType = Literal["SPLIT", "BONUS", "DIVIDEND"]


class CorporateAction(BaseModel):
    id: Optional[int] = None
    instrumentId: str
    actionType: CorporateActionType
    ratioFrom: Optional[float] = None
    ratioTo: Optional[float] = None
    dividendAmount: Optional[float] = None
    exDate: str                        # YYYY-MM-DD
    isApplied: bool = False
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Dataset Versions & Lineage
# ---------------------------------------------------------------------------


class DatasetVersion(BaseModel):
    id: str                            # e.g. "sim-in-eq-20240821"
    name: str
    description: str
    source: str                        # "SIMULATOR" | "NSE_EOD" | "ANGEL_HISTORICAL"
    symbolCount: int
    barCount: int
    startTimeMs: int
    endTimeMs: int
    checksum: str                      # SHA256 hash
    isImmutable: bool = True
    createdAt: Optional[str] = None


# ---------------------------------------------------------------------------
# Data Quality & Validation Reports
# ---------------------------------------------------------------------------

DataQualityStatus = Literal["PASS", "WARN", "FAIL"]


class DataQualityReport(BaseModel):
    id: Optional[int] = None
    datasetVersionId: str
    generatedAt: Optional[str] = None
    status: DataQualityStatus
    missingCandles: int = 0
    duplicateCandles: int = 0
    outlierTicks: int = 0
    corporateActionsApplied: int = 0
    notes: str = ""
    metrics: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Historical Bar Queries & Responses
# ---------------------------------------------------------------------------


class HistoricalBarRecord(BaseModel):
    t: int                             # timestamp in ms
    o: float
    h: float
    l: float
    c: float
    v: float
    vwap: Optional[float] = None
    isAdjusted: bool = True


class HistoricalBarQuery(BaseModel):
    symbol: str
    timeframe: Timeframe = "1D"
    startTimeMs: Optional[int] = None
    endTimeMs: Optional[int] = None
    limit: int = 520
    adjusted: bool = True
    datasetVersion: Optional[str] = None


class DataAuditRequest(BaseModel):
    datasetVersionId: str
    maxOutlierMovePct: float = 0.10    # 10% unconfirmed single-bar jump
    checkSessionContinuity: bool = True
