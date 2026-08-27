# AURA V2 — Full Code Audit
**Date:** 2026-08-27  
**Auditor:** Automated (pre-V2 transformation)  
**Baseline commit:** `bdb65c5`  
**Test count at audit time:** 231 passing

---

## 1. Current Architecture Summary

```
AURA V1 Architecture
├── Frontend: React 19 + Vite + TanStack Router/Query
├── Backend: FastAPI + Uvicorn + Pydantic v2
├── Decision: engines/decision/ (parity-tested vs TS source)
├── Risk: engines/risk/risk.py (snapshot_risk — 6 rules)
├── Paper: paper/book.py + matching.py (server-authoritative)
├── Quant: quant/base_strategy.py (delegates to engines/)
├── Research: research/backtester.py + walk_forward.py
├── ML: ml/ (heuristic regime + direction + Platt calibration + PSI drift)
├── Similarity: similarity/ (cosine vector store + 8 named patterns)
├── Broker: broker/order_router.py + openalgo_client.py (live-gated)
├── Realtime: realtime/ (event bus + WebSocket gateway + tick ingest)
├── Data: data/simulator.py + store.py + master.py + quality.py
└── DB: PostgreSQL via SQLAlchemy (6 migration files)
```

---

## 2. Module-by-Module Findings

### 2.1 `engines/decision/indicators.py`
**Type:** Real implementation (parity-tested)  
**Issues:**
- `rsi()` uses simple average (Wilder's smoothing not implemented) — diverges from true RSI for longer series. **MEDIUM**
- `adx_pack()` uses simple moving average instead of Wilder's smoothed average — ADX values systematically lower than canonical. **MEDIUM**
- `_ema()` starts from `xs[0]` (no warmup period) — biased for short series. **LOW**
- No ATR-based position sizing anywhere. **HIGH** (missing)
- No ROC, momentum persistence, Bollinger width as separate features. **MEDIUM** (missing)

### 2.2 `engines/decision/regime.py`
**Type:** Rule-based heuristic  
**Issues:**
- Returns only a label + single scalar fields. No probability distribution. **HIGH**
- Regime is hard if/elif cascade — no uncertainty, no "BULL_TREND: 0.62, BREAKOUT: 0.21" semantics. **HIGH**
- `vol > 0.32 → STRESS` threshold is a hard cut, not calibrated. **MEDIUM**
- No model_version tracking on regime output. **MEDIUM**
- STRESS suppresses all actions; no partial confidence reduction. **MEDIUM**
- No regime confidence score. **HIGH**

### 2.3 `engines/decision/strategies.py`
**Type:** Real, parity-tested  
**Issues:**
- Returns `StrategyOutput` with `action`, `confidence`, `reason`, `invalidation` — but NO `expected_R`, NO `feature_evidence` list, NO `regime_fit` score embedded in signal. **HIGH**
- `confidence` is computed from simple linear formulas — not calibrated against outcomes. **HIGH**
- No `strategy_version` tagging in output beyond string. **LOW**
- All three strategies share the same `compute_indicators()` call — no feature caching, computed 3× per decision cycle. **MEDIUM** (perf)

### 2.4 `engines/decision/decision.py`
**Type:** Real, parity-tested  
**Issues:**
- `_dir_probs()` is purely heuristic — constants (0.33, 0.45, 0.25, 0.06) are not data-derived. **HIGH**
- `_pick_best()` selects one strategy and discards the others — no ensemble voting. **HIGH**
- No `NO_TRADE` action — system only outputs BUY/SELL/HOLD/SKIP. **HIGH**
- No `expected_edge_bps` calculation. **HIGH**
- `risk_level` string is heuristic, not connected to the real risk engine. **HIGH**
- `decide_universe()` imports `bars_of` from simulator — couples decision engine to simulator. **MEDIUM**
- No `DecisionExplanation` / structured explanation object. **HIGH**

### 2.5 `paper/matching.py`
**Type:** Real implementation  
**Issues:**
- Only handles `LIMIT` orders. `MARKET` orders are not implemented — `place_order()` in `book.py` always sets `type="LIMIT"`. **CRITICAL**
- No slippage model (market impact, spread crossing). **HIGH**
- No partial fills. **MEDIUM**
- No order expiry / Good-Till-Cancelled logic. **MEDIUM**
- No SL-M (stop-market) or SL (stop-limit) order types. **HIGH**
- Stop-loss check uses `quote.ltp` exactly — no gap-through simulation. **MEDIUM**
- `bid/ask` from Quote model default to 0.0 — if not populated, ask=ltp which is unrealistic. **MEDIUM**

### 2.6 `paper/book.py`
**Type:** Real implementation  
**Issues:**
- `place_order()` signature always creates `type="LIMIT"` regardless of request. **CRITICAL**
- No MARKET order execution path. **CRITICAL**
- Position WAP (weighted average price) accounting appears correct. **OK**
- `process_market_tick()` calls `check_position_stops()` — correct. **OK**
- `get_risk_snapshot()` called inside `place_order()` using `env="PAPER"` hardcoded — correct. **OK**
- No max holding period / position age tracking. **LOW**

### 2.7 `engines/risk/risk.py`
**Type:** Real, well-tested  
**Issues:**
- All 6 rules implemented and tested. **OK**
- `DEFAULT_LIMITS.stopRequired` exists but is False — stop-loss is not enforced by default. **MEDIUM** (configurable, but surprising)
- No per-trade risk cap (risk per trade as % of equity). **HIGH**
- No sector exposure cap. **MEDIUM**
- No max consecutive loss tracking. **MEDIUM**
- No volatility-adjusted position sizing input. **HIGH**
- No model-confidence halt rule. **MEDIUM**
- No strategy drawdown circuit breaker. **MEDIUM**

### 2.8 `research/backtester.py`
**Type:** Real implementation  
**Issues:**
- Causality tested (no lookahead). **OK**
- Cost model applied. **OK**
- `_exit_signal()` checks stop/target but uses `bar.c` (close) — stop breaches that happen intrabar (bar.l crosses stop) are not detected. **HIGH** (OHLC assumption issue)
- No Monte Carlo trade reshuffling. **MEDIUM**
- No parameter sensitivity analysis. **MEDIUM**
- No regime-conditional backtesting. **HIGH** (missing)
- Sharpe uses annualization factor 252 — correct. **OK**
- No CAGR, Sortino, Calmar, CVaR in current metrics. **MEDIUM**
- Survivorship bias: uses simulator data which is fixed — not from real market. **MEDIUM** (noted)

### 2.9 `research/walk_forward.py`
**Type:** Real implementation  
**Issues:**
- Walk-forward implemented correctly. **OK**
- No out-of-sample test separation enforcement. **MEDIUM**
- No fold-level regime breakdown. **MEDIUM**

### 2.10 `ml/regime_model.py` and `ml/direction_model.py`
**Type:** Heuristic (labeled as ML but no trained model)  
**Issues:**
- `RegimeClassifier` is a rule-based classifier using ADX/vol/RSI thresholds — functionally identical to `engines/decision/regime.py` with probability wrapping. **HIGH** (confusion)
- `DirectionModel` uses RSI/MACD thresholds with softmax normalization — not a trained model. **HIGH** (misleading name)
- No training data, no training pipeline, no model serialization. **HIGH**
- No model registry, no versioning, no lifecycle management. **HIGH**
- Calibration (Platt/isotonic) is implemented but never trained on real outcome data. **HIGH**
- `ml/drift_monitor.py` PSI implementation is correct but operates on synthetic distributions. **MEDIUM**

### 2.11 `similarity/vector_store.py`
**Type:** Real implementation  
**Issues:**
- In-memory only — not persisted between restarts. **HIGH**
- Max 10,000 entries with LRU eviction — reasonable. **OK**
- Cosine similarity is correct. **OK**
- No sample size minimum enforcement on query results. **HIGH** (per spec)
- `tag_outcome()` exists but no post-trade analysis loop feeds it. **HIGH**

### 2.12 `broker/order_router.py`
**Type:** Real implementation (recently fixed)  
**Issues:**
- `snapshot_risk()` called before routing. **OK**
- PAPER path uses real `book.py`. **OK**
- LIVE path live-gated. **OK**
- No cancel/replace logic. **LOW**
- Audit log in-memory only. **MEDIUM**

### 2.13 `data/simulator.py`
**Type:** Simulator (expected)  
**Issues:**
- `bars_of()` generates deterministic synthetic OHLCV — no real market data integration. **HIGH** (by design for now, but must be abstracted)
- No market holiday handling. **MEDIUM**
- No corporate action adjustments. **MEDIUM**
- No bid/ask spread simulation in `quotes_now()`. **MEDIUM**
- No session-phase tagging (pre-market, open, close). **LOW**

### 2.14 `data/quality.py`
**Type:** Real implementation  
**Issues:**
- Duplicate-bar detection exists. **OK**
- Missing-bar detection exists. **OK**
- Timestamp validation exists. **OK**
- No outlier detection (price spike > N×ATR). **MEDIUM**
- No timezone normalization. **LOW**
- Quality checks not wired into the decision pipeline. **HIGH** — data can reach strategies without passing quality checks.

### 2.15 Frontend (`src/routes/`)
**Type:** Real React implementation  
**Issues:**
- Dashboard shows decisions from `/api/universe/decisions`. **OK**
- Paper trading UI exists. **OK**
- Risk monitor exists. **OK**
- Strategy Lab exists. **OK**
- No "WHY BUY?" explainability panel. **HIGH**
- No ensemble decision breakdown visible to user. **HIGH**
- No model health indicators. **HIGH**
- No data quality health panel. **HIGH**
- No execution quality monitoring. **HIGH**
- Charts exist but are decorative (minimal actionable information). **MEDIUM**

### 2.16 Security
**Issues:**
- No hardcoded secrets found in source. **OK**
- CORS not configured in `main.py` (accepts all origins in dev). **MEDIUM**
- No authentication on any API endpoint. **HIGH** (paper mode only, acceptable for now)
- `AURA_LIVE_TRADING` env var is the only live gate — no secondary confirmation. **MEDIUM**
- No audit of whether `OPENALGO_API_KEY` is logged anywhere. **MEDIUM**

### 2.17 Observability
**Issues:**
- No structured logging (uses Python `logging` module with basic format). **HIGH**
- No event_id / request_id on API calls. **MEDIUM**
- No `/health` endpoint checking DB, broker, ML, data freshness. **MEDIUM**
- No latency tracking on decision computation. **LOW**

### 2.18 Testing
**Issues:**
- 231 tests passing. **OK**
- No property/invariant tests. **HIGH**
- No order-type semantic tests (MARKET vs LIMIT). **CRITICAL**
- No position sizing tests. **HIGH**
- No ensemble decision tests. **HIGH**
- No feature alignment / no-lookahead tests for new feature engine. **HIGH**
- No live-trading protection invariant test. **HIGH**

---

## 3. Issue Classification Summary

| Severity | Count | Key Items |
|----------|-------|-----------|
| **CRITICAL** | 3 | MARKET orders not implemented; order type silently converted; no order-type tests |
| **HIGH** | 28 | No NO_TRADE action; no ensemble; no expected value; no position sizing; no per-trade risk cap; no calibrated probabilities; ML modules are heuristics; no regime probabilities; no explainability; quality checks not wired; similarity no sample-size gate; no post-trade loop; no model registry |
| **MEDIUM** | 18 | RSI/ADX use non-Wilder smoothing; backtester OHLC stop detection; audit log in-memory; no CORS config; no structured logging; no health endpoints; no Monte Carlo; no Sortino/Calmar/CVaR |
| **LOW** | 6 | EMA warmup bias; no position age; no cancel/replace; no session phase tagging; no timezone normalization; code comments reference TS source |

**Total issues identified: 55**

---

## 4. Duplicate Logic Map

| Logic | Location 1 | Location 2 | Status |
|-------|-----------|-----------|--------|
| Strategy evaluate() | `engines/decision/strategies.py` | `quant/base_strategy.py` | **FIXED** — quant delegates to engines |
| Regime classification | `engines/decision/regime.py` | `ml/regime_model.py` | **DIVERGED** — different thresholds, different output schema |
| Indicator computation | `engines/decision/indicators.py` | `quant/features.py` | **PARTIAL** — features.py extends indicators.py |

---

## 5. Execution Model Issues

1. **MARKET orders silently become LIMIT** — `book.py` `place_order()` always sets `type="LIMIT"`. A MARKET order should execute at current ask/bid immediately, no limit. **CRITICAL**
2. **No slippage** — fills at exact ask/bid with no market impact model.
3. **Stop-loss uses close price** — a bar where `low < stop` but `close > stop` will NOT trigger the stop. Real execution would trigger at `stop` price intrabar.
4. **No partial fills** — all orders are all-or-nothing.
5. **No order expiry** — orders stay OPEN indefinitely.

---

## 6. Backtesting Weaknesses

1. **OHLC stop assumption** — uses `bar.c` for exit; should use `bar.l` (for longs) to detect intrabar stop breach.
2. **No Monte Carlo** — single path, no trade reshuffling.
3. **Metrics incomplete** — missing Sortino, Calmar, CVaR, CAGR, Tail Loss, Turnover.
4. **No regime-conditional analysis** — can't see "ORB works in BREAKOUT regime, fails in RANGE."
5. **No out-of-sample enforcement** — walk-forward exists but nothing prevents overfitting on full dataset.

---

## 7. Data Quality Weaknesses

1. Quality checks (`data/quality.py`) exist but are **never called** in the decision pipeline.
2. No outlier detection (gap > 3×ATR, price spike).
3. No bid/ask spread simulation.
4. Simulator returns same bars every call — deterministic, not realistic.

---

## 8. Implementation Order for V2

Based on severity and dependency order:

```
A. Phase 0  — This audit ✓
B. Phase 1  — Fix MARKET/LIMIT/SL/SL-M order semantics (CRITICAL)
C. Phase 2  — Wire data quality into decision pipeline (HIGH)
D. Phase 3  — Feature engine with no-lookahead guarantee (HIGH)
E. Phase 4  — Regime engine with probability output (HIGH)
F. Phase 5  — Strategy evidence layer (HIGH)
G. Phase 6  — Ensemble decision engine + NO_TRADE (HIGH)
H. Phase 7  — Expected value engine (HIGH)
I. Phase 8  — Position sizing engine (HIGH)
J. Phase 9  — Expanded portfolio risk (HIGH)
K. Phase 10 — Backtester upgrades (intrabar stops, metrics) (HIGH)
L. Phase 11 — Regime-conditional backtesting (HIGH)
M. Phase 12 — Similarity memory upgrade (MEDIUM)
N. Phase 13 — Post-trade learning loop (HIGH)
O. Phase 14 — ML training architecture (HIGH)
P. Phase 15/16 — Calibration + drift (MEDIUM)
Q. Phase 17 — News/context abstraction (MEDIUM)
R. Phase 18 — Strategy allocation engine (HIGH)
S. Phase 19 — Frontend explainability (HIGH)
T. Phase 20 — Observability (MEDIUM)
U. Phase 21 — Security audit (MEDIUM)
V. Phase 22/23 — Testing + invariants (HIGH)
W. Phase 24 — Documentation (MEDIUM)
X. Phase 25 — Final verification (required)
```
