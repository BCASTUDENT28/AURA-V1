export type Action = "BUY" | "SELL" | "HOLD" | "SKIP";
export type InstrumentKind = "index" | "equity";
export type Timeframe = "5m" | "1D";
export type OrderSide = "BUY" | "SELL";
export type OrderStatus = "PENDING" | "FILLED" | "REJECTED" | "CANCELLED";
export type ProductType = "INTRADAY" | "DELIVERY";

export type RegimeLabel =
  | "BULL_TREND"
  | "BEAR_TREND"
  | "RANGE"
  | "HIGH_VOL"
  | "LOW_VOL"
  | "BREAKOUT"
  | "MEAN_REVERT"
  | "STRESS";

export interface Instrument {
  symbol: string;
  name: string;
  sector: string;
  kind: InstrumentKind;
  base: number;
  tick: number;
  lot: number;
  avgVolume: number;
}

export interface Bar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface Quote {
  symbol: string;
  ltp: number;
  bid: number;
  ask: number;
  open: number;
  high: number;
  low: number;
  prevClose: number;
  change: number;
  changePct: number;
  volume: number;
  ts: number;
}

export interface Indicators {
  smaFast: number;
  smaSlow: number;
  ema9: number;
  ema21: number;
  rsi: number;
  macd: number;
  macdSignal: number;
  atr: number;
  adx: number;
  plusDi: number;
  minusDi: number;
  vwap: number;
  bbUpper: number;
  bbLower: number;
  bbMid: number;
  realizedVol: number;
  volumeZ: number;
  relVolume: number;
}

export interface Regime {
  label: RegimeLabel;
  adx: number;
  realizedVol: number;
  volPercentile: number;
  trendStrength: number;
  notes: string;
}

export interface StrategyConfig {
  [key: string]: number;
}

export interface StrategyOutput {
  strategyId: string;
  version: string;
  action: Action;
  entry: number | null;
  stop: number | null;
  target: number | null;
  confidence: number;
  reason: string;
  invalidation: string;
  metadata: Record<string, number | string>;
}

export interface SimilarMatch {
  n: number;
  winRate: number;
  avgReturn: number;
  avgMae: number;
  avgMfe: number;
  avgHoldBars: number;
}

export interface Evidence {
  text: string;
  kind: "support" | "contradict" | "neutral";
}

export interface Decision {
  id: string;
  symbol: string;
  ts: number;
  action: Action;
  probabilityUp: number;
  probabilityDown: number;
  probabilityNeutral: number;
  confidence: number;
  risk: "LOW" | "MODERATE" | "HIGH" | "BLOCKED";
  expectedRR: number | null;
  entry: number | null;
  stop: number | null;
  target: number | null;
  invalidation: string;
  reasons: Evidence[];
  contradictions: Evidence[];
  strategy: StrategyOutput;
  regime: Regime;
  similar: SimilarMatch;
  riskReasons: string[];
  lineage: {
    strategyVersion: string;
    modelVersion: string;
    featureVersion: string;
    datasetVersion: string;
    costVersion: string;
  };
}

export interface CostBreakdown {
  brokerage: number;
  stt: number;
  stamp: number;
  exchange: number;
  sebi: number;
  gst: number;
  slippage: number;
  total: number;
}

export interface BacktestTrade {
  symbol: string;
  side: OrderSide;
  entryTs: number;
  exitTs: number;
  entry: number;
  exit: number;
  qty: number;
  pnl: number;
  pnlPct: number;
  rMultiple: number;
  costs: number;
  reason: string;
  regime: RegimeLabel;
}

export interface BacktestMetrics {
  trades: number;
  wins: number;
  losses: number;
  winRate: number;
  lossRate: number;
  totalReturn: number;
  cagr: number;
  netPnl: number;
  profitFactor: number;
  expectancy: number;
  avgR: number;
  sharpe: number;
  sortino: number;
  maxDrawdown: number;
  recoveryFactor: number;
  avgHoldBars: number;
  bestTrade: number;
  worstTrade: number;
  costsTotal: number;
  monthly: { month: string; ret: number }[];
  byRegime: { regime: RegimeLabel; trades: number; winRate: number; pnl: number }[];
  equity: { t: number; v: number }[];
}

export interface BacktestResult {
  strategyId: string;
  version: string;
  symbol: string;
  timeframe: Timeframe;
  from: number;
  to: number;
  config: StrategyConfig;
  product: ProductType;
  metrics: BacktestMetrics;
  trades: BacktestTrade[];
  walkForward: {
    window: string;
    train: string;
    test: string;
    testReturn: number;
    testWinRate: number;
    testSharpe: number;
  }[];
  robust: {
    neighborStd: number;
    warning: string | null;
  };
}

export interface PaperOrder {
  id: string;
  ts: number;
  symbol: string;
  side: OrderSide;
  type: "LIMIT";
  qty: number;
  limitPrice: number;
  status: OrderStatus;
  fillPrice: number | null;
  costs: CostBreakdown | null;
  rejectReason: string | null;
  strategyId: string | null;
  stop: number | null;
  target: number | null;
}

export interface PaperPosition {
  symbol: string;
  qty: number;
  avgPrice: number;
  side: OrderSide;
  stop: number | null;
  target: number | null;
  openedTs: number;
  realized: number;
  costs: number;
  strategyId: string | null;
}

export interface PaperFill {
  id: string;
  orderId: string;
  ts: number;
  symbol: string;
  side: OrderSide;
  qty: number;
  price: number;
  costs: CostBreakdown;
}

export interface Learning {
  id: string;
  ts: number;
  kind: "SUCCESS" | "FAILURE" | "REGIME" | "RISK" | "EXECUTION";
  setup: string;
  strategyId: string;
  strategyVersion: string;
  modelVersionId?: string;
  featureVersionId?: string;
  datasetVersionId?: string;
  minSampleRequired?: number;
  regime: RegimeLabel;
  symbol: string;
  evidence: string;
  sampleSize: number;
  confidence: number;
  expiresTs: number;
  rMultiple: number | null;
}

export interface NewsItem {
  id: string;
  ts: number;
  headline: string;
  source: string;
  symbols: string[];
  sentiment: number;
  event: string;
  impact: "LOW" | "MEDIUM" | "HIGH";
}

export interface RiskLimits {
  maxPositionPct: number;
  maxDailyLossPct: number;
  maxExposurePct: number;
  maxPositions: number;
  maxSectorPct: number;
  opsPerSec: number;
  stopRequired: boolean;
  limitOnly: boolean;
  dataFreshMs: number;
}

export interface RiskSnapshot {
  killSwitch: boolean;
  dailyPnl: number;
  dailyPnlPct: number;
  exposurePct: number;
  openPositions: number;
  dataAgeMs: number;
  opsWindow: number[];
  staticIpOk: boolean;
  env: "PAPER";
  livePathSealed: boolean;
  dataSource: "SIMULATOR";
  breaches: string[];
  canTrade: boolean;
}

export const FEATURE_VERSION = "feat-v1";
export const DATASET_VERSION = "sim-in-eq-20240821";
export const MODEL_VERSION = "regime-rules-v1";
export const COST_VERSION = "in-cash-2026-unverified-v1";
export const STARTING_CASH = 1_000_000;
