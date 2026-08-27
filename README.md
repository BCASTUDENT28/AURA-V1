# AURA V1 — AI-Powered Algorithmic Trading Platform

> **Status: Paper trading ready. Live trading disabled by design.**
> `AURA_LIVE_TRADING` must not be set until Angel One account, static IP, and API key are configured.

AURA (Automated Universal Risk-aware Algorithm) is a full-stack, production-architecture algorithmic trading platform for Indian equity markets (NSE/BSE/NFO/MCX via Angel One + OpenAlgo). It combines a parity-verified decision engine, multi-strategy framework, paper trading simulator, backtester, ML regime classification, similarity/pattern memory, and a real-time React dashboard — all backed by 231 automated tests.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Feature Phases](#feature-phases)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Running the App](#running-the-app)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Database Migrations](#database-migrations)
- [Risk Engine — Rules & Safety](#risk-engine--rules--safety)
- [Live Trading — How to Enable](#live-trading--how-to-enable)
- [Architecture Decisions](#architecture-decisions)
- [Branches](#branches)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    React Frontend (Vite + TanStack)          │
│  Dashboard │ Paper │ Risk │ Strategy Lab │ Research │ Memory │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP / WebSocket
┌─────────────────────▼───────────────────────────────────────┐
│              FastAPI Backend (Python 3.13)                   │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │  Decision   │  │  Risk Engine │  │   Paper Book       │ │
│  │  Engine     │  │  (6 rules)   │  │   (Matching Eng.)  │ │
│  │  (parity ✓) │  │              │  │                    │ │
│  └──────┬──────┘  └──────┬───────┘  └────────────────────┘ │
│         │                │                                  │
│  ┌──────▼──────┐  ┌──────▼───────┐  ┌────────────────────┐ │
│  │  Strategy   │  │  Order Router│  │   ML Layer         │ │
│  │  Framework  │  │  (risk-gated)│  │   (regime/drift)   │ │
│  │  3 strategies│  │              │  │                    │ │
│  └─────────────┘  └──────────────┘  └────────────────────┘ │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ Backtester  │  │  Similarity  │  │  Real-Time Engine  │ │
│  │ Walk-Forward│  │  (Vector DB) │  │  WebSocket / Ticks │ │
│  └─────────────┘  └──────────────┘  └────────────────────┘ │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │          OpenAlgo Broker Client (LIVE-GATED)        │   │
│  │          AURA_LIVE_TRADING=1 required               │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Feature Phases

### Phase 1 — Decision Engine (Parity-Verified)
- Python port of the original TypeScript decision engine, byte-for-byte parity tested
- `compute_decision(symbol, bars, strategy_id, config)` → deterministic `DecisionOutput`
- Identical thresholds, constants, and logic branch order as the TS source
- **Tests:** `test_decision_parity.py` (8 tests, deterministic seeded simulation)

### Phase 2 — Risk Engine
- `snapshot_risk()` — single function computing `RiskSnapshot` with `canTrade` flag
- **6 enforced rules:**
  1. Kill switch (manual emergency stop)
  2. Daily loss circuit breaker (−2% of starting capital)
  3. Portfolio exposure cap (80% NAV)
  4. Max simultaneous positions (5)
  5. Stale market data check (>5 seconds)
  6. 9 ops/sec throttle (Angel One hard cap)
- Static IP check: only enforced for `env=LIVE`, not PAPER/DEV
- **Tests:** `test_risk.py`, `test_paper_risk_gating.py`

### Phase 3 — Strategy Framework & Strategy Lab
- `BaseStrategy` ABC with `evaluate(bars, features) → StrategySignal`
- **3 strategies** (all delegate to Phase 1 parity-tested functions — single source of truth):
  - `MACrossoverStrategy` — 9/21 SMA crossover with ADX filter
  - `VWAPRSIStrategy` — VWAP + RSI momentum continuation
  - `OpeningRangeBreakoutStrategy` — ORB with volume expansion
- Strategy Lab API: run any strategy on any symbol, get signals, brackets, regime fit
- **Tests:** `test_strategies_framework.py`, `test_quant_regimes.py`

### Phase 4 — Backtester & Walk-Forward
- `CausalBacktester` — strict bar-by-bar causality (no lookahead)
- Full Indian broker cost model: STT, SEBI fee, NSE fee, GST, stamp duty, brokerage
- Metrics: Sharpe, Calmar, max drawdown, win rate, average R-multiple
- Walk-forward validation across rolling windows
- **Tests:** `test_backtest_causality.py`, `test_backtest_metrics.py`, `test_walk_forward.py`

### Phase 5 — Paper Trading Engine
- `PaperBookStore` — server-authoritative portfolio: cash, positions, P&L
- `PaperMatchingEngine` — limit order matching against simulated quotes
- Risk gating on every `place_order()` call (second gate, uses same `snapshot_risk()`)
- Order lifecycle: OPEN → FILLED / CANCELLED
- Session management (archive + reset)
- **Tests:** `test_paper_matching.py`, `test_paper_positions.py`, `test_paper_risk_gating.py`

### Phase 6 — Real-Time Engine
- `EventBus` — async pub/sub (market data, signals, fills, risk events)
- `TickGateway` — WebSocket endpoint, broadcasts live ticks to subscribed clients
- `TickIngestor` — normalises and routes incoming tick data
- **Tests:** `test_realtime_event_bus.py`, `test_realtime_gateway.py`, `test_realtime_tick_ingest.py`

### Phase 7 — ML Layer
- `RegimeClassifier` — probabilistic regime detection (BULL_TREND, BEAR_TREND, BREAKOUT, RANGE, LOW_VOL, HIGH_VOL, STRESS, MEAN_REVERT)
- `DirectionModel` — BUY/SELL/FLAT signal with confidence and edge BPS
- `PlattCalibrator` / `IsotonicCalibrator` — probability calibration for confidence scores
- `FeatureDriftMonitor` — PSI-based drift detection with z-score alerts
- **Tests:** `test_ml_regime.py`, `test_ml_calibration.py`, `test_ml_drift.py`

### Phase 8 — Similarity & Evidence Memory
- `VectorStore` — cosine-similarity in-memory store with outcome tagging
- `PatternLibrary` — 8 named patterns (momentum surge, panic capitulation, coiling spring, etc.)
- Outcome tagging: tag any stored pattern as WIN/LOSS for forward learning
- **Tests:** `test_similarity.py`

### Phase 9 — Broker Integration (Live-Gated)
- `OpenAlgoClient` — HTTP wrapper for OpenAlgo REST API (Angel One adapter)
- `OrderRouter` — routes orders through:
  1. Static validation (action, qty, exchange, orderType)
  2. **`snapshot_risk()` gate** — must pass before any routing
  3. `env=PAPER` → real `paper/book.py` matching engine
  4. `env=LIVE` → OpenAlgo broker (requires `AURA_LIVE_TRADING=1`)
- Full audit log with `riskCanTrade`, `riskBreaches`, latency on every entry
- **Tests:** `test_broker.py`

### Architecture Fixes (Post-Review)
- **Branch unification:** `master` and `main` identical at `4636e1b`
- **Strategy unification:** `quant/base_strategy.py` delegates to `engines/decision/strategies.py` — zero duplicate logic, one source of truth
- **Risk gate wired:** `order_router.py` calls `snapshot_risk()` on every order path (PAPER + LIVE)
- **PAPER path fixed:** `/api/broker/order` with `env=PAPER` routes through real `book.py` (not fake simulation)

---

## Tech Stack

### Backend
| Package | Version | Purpose |
|---------|---------|---------|
| Python | 3.13 | Runtime |
| FastAPI | ≥0.111 | REST API + WebSocket |
| Uvicorn | ≥0.29 | ASGI server |
| Pydantic | ≥2.7 | Data validation & schemas |
| SQLAlchemy | ≥2.0 | ORM (Postgres) |
| psycopg2-binary | ≥2.9 | Postgres driver |
| pytest | ≥8.0 | Test runner (231 tests) |
| httpx | ≥0.27 | Async HTTP (broker client) |

### Frontend
| Package | Purpose |
|---------|---------|
| React 19 | UI framework |
| Vite + TanStack Start | Build + routing |
| TanStack Router / Query / Table | Data fetching, routing, tables |
| Tailwind v4 | Styling |
| Radix UI | Accessible components |
| Zustand | Client state |
| Zod | Schema validation |

### Database
- **PostgreSQL** — persistent storage (risk events, market data, backtest runs, paper engine state)
- 6 migration files in `migrations/`

---

## Project Structure

```
AURA-V1/
├── backend/
│   ├── app/
│   │   ├── api/routes/          # FastAPI route handlers
│   │   │   ├── broker.py        # /api/broker — order routing
│   │   │   ├── market_data.py   # /api/market — quotes, OHLCV
│   │   │   ├── ml.py            # /api/ml — regime, direction, drift
│   │   │   ├── paper.py         # /api/paper — paper book, orders
│   │   │   ├── quant.py         # /api/quant — strategy lab, signals
│   │   │   ├── realtime.py      # /api/realtime — WebSocket ticks
│   │   │   ├── research.py      # /api/research — backtester, walk-forward
│   │   │   └── similarity.py    # /api/similarity — pattern memory
│   │   ├── broker/
│   │   │   ├── openalgo_client.py   # OpenAlgo HTTP client (live-gated)
│   │   │   └── order_router.py      # Risk-gated order dispatcher
│   │   ├── data/
│   │   │   ├── master.py        # Instrument master (NSE/NFO universe)
│   │   │   ├── quality.py       # Data quality checks
│   │   │   ├── simulator.py     # Quote simulator for paper/dev
│   │   │   └── store.py         # Market data store
│   │   ├── engines/
│   │   │   ├── cost/cost.py     # Indian broker cost model
│   │   │   ├── decision/        # ← Parity-tested decision engine
│   │   │   │   ├── decision.py  # compute_decision() — main entry point
│   │   │   │   ├── indicators.py
│   │   │   │   ├── regime.py
│   │   │   │   └── strategies.py  # ma_cross(), vwap_rsi(), orb() — single source of truth
│   │   │   └── risk/risk.py     # snapshot_risk() — the risk gate
│   │   ├── ml/
│   │   │   ├── calibration.py   # Platt + isotonic calibrators
│   │   │   ├── direction_model.py
│   │   │   ├── drift_monitor.py # PSI-based feature drift
│   │   │   └── regime_model.py
│   │   ├── paper/
│   │   │   ├── book.py          # PaperBookStore — authoritative portfolio state
│   │   │   ├── matching.py      # PaperMatchingEngine — limit order matching
│   │   │   └── session.py       # Session lifecycle
│   │   ├── quant/
│   │   │   ├── base_strategy.py # BaseStrategy ABC + 3 concrete strategies (delegate to engines/)
│   │   │   ├── features.py      # FeatureVector + extract_features()
│   │   │   └── regime_engine.py # QuantRegimeEngine
│   │   ├── realtime/
│   │   │   ├── event_bus.py
│   │   │   ├── gateway.py       # WebSocket tick gateway
│   │   │   └── tick_ingest.py
│   │   ├── research/
│   │   │   ├── backtester.py    # CausalBacktester
│   │   │   ├── metrics.py       # Sharpe, Calmar, drawdown
│   │   │   └── walk_forward.py
│   │   ├── schemas/types.py     # All shared Pydantic schemas
│   │   └── main.py              # FastAPI app, router mounts
│   ├── tests/                   # 20 test files, 231 tests total
│   └── requirements.txt
├── migrations/
│   ├── 0002_aura_core.sql       # Core tables (signals, decisions)
│   ├── 0003_phase1_risk_events.sql
│   ├── 0004_market_data.sql
│   ├── 0005_backtest_runs.sql
│   └── 0006_paper_engine.sql
├── src/                         # React frontend
│   ├── routes/
│   │   ├── index.tsx            # Dashboard — universe overview, decisions
│   │   ├── paper.tsx            # Paper trading UI
│   │   ├── risk.tsx             # Risk monitor
│   │   ├── lab.tsx              # Strategy Lab
│   │   ├── research.tsx         # Backtester UI
│   │   ├── memory.tsx           # Similarity / pattern memory
│   │   ├── signals.tsx          # Live signals feed
│   │   ├── gap.tsx              # Gap analysis
│   │   └── news.tsx             # Market news
│   ├── components/aura/         # AURA-specific UI components
│   └── styles.css
└── tests/                       # Top-level tests (ML, similarity, broker)
```

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ (optional — app runs without DB in simulator mode)

### Backend Setup

```bash
# 1. Create virtual environment
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Set environment variables
# Copy and fill in your values:
# DATABASE_URL=postgresql://user:password@localhost:5432/aura
# OPENALGO_API_KEY=your_key_here        # Only for live trading
# AURA_LIVE_TRADING=0                   # Keep 0 until ready
```

### Frontend Setup

```bash
# From repo root
npm install
```

---

## Running the App

### Development (both servers)

**Backend:**
```bash
cd backend
.venv\Scripts\activate         # Windows
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Frontend:**
```bash
# From repo root
npm run dev
# Starts at http://localhost:3000
```

### API Docs
FastAPI auto-generates interactive docs:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

---

## API Reference

### Decision Engine
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/universe/decisions` | All symbol decisions with regime + signals |
| GET | `/api/universe/signals/{symbol}` | Single symbol full decision output |

### Paper Trading
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/paper/book` | Portfolio state (cash, positions, P&L) |
| POST | `/api/paper/order` | Place paper order (risk-gated) |
| POST | `/api/paper/cancel` | Cancel open order |
| POST | `/api/paper/reset` | Reset portfolio to starting capital |
| POST | `/api/paper/match-tick` | Process market tick (fill open orders) |
| GET | `/api/paper/session` | Current session info |

### Risk
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/paper/risk` | Live `RiskSnapshot` with `canTrade` + breach list |

### Strategy Lab (Quant)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/quant/strategies` | List all strategies with default params |
| POST | `/api/quant/run` | Run strategy on symbol, get signal + bracket |
| POST | `/api/quant/grid` | Parameter grid search across strategy configs |

### Backtester
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/research/backtest` | Run backtest (symbol, strategy, date range) |
| POST | `/api/research/walk-forward` | Walk-forward validation |
| GET | `/api/research/runs` | List historical backtest runs |

### ML
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ml/regime/{symbol}` | Probabilistic regime classification |
| GET | `/api/ml/direction/{symbol}` | BUY/SELL/FLAT signal with confidence |
| GET | `/api/ml/drift` | Feature drift report (PSI per feature) |
| POST | `/api/ml/calibrate` | Calibrate confidence scores (Platt/isotonic) |

### Similarity / Pattern Memory
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/similarity/store` | Store feature vector for a symbol+bar |
| POST | `/api/similarity/query` | Find similar historical patterns |
| POST | `/api/similarity/tag` | Tag a stored pattern as WIN/LOSS |
| GET | `/api/similarity/patterns` | Run all 8 named patterns on current bar |
| GET | `/api/similarity/stats` | Vector store statistics |

### Broker (Order Routing)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/broker/order` | Route order (PAPER → book.py, LIVE → OpenAlgo) |
| GET | `/api/broker/audit` | Order audit log with risk fields |
| GET | `/api/broker/status` | Broker connection + live trading status |
| GET | `/api/broker/positions` | Live positions (requires LIVE enabled) |
| GET | `/api/broker/funds` | Account funds (requires LIVE enabled) |

### Market Data
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/market/quotes` | Current simulated quotes for all symbols |
| GET | `/api/market/ohlcv/{symbol}` | OHLCV bars (1D, 1H, 15m) |
| GET | `/api/market/master` | Instrument master (universe) |

### Real-Time
| Method | Endpoint | Description |
|--------|----------|-------------|
| WebSocket | `/ws/ticks` | Live tick stream |
| POST | `/api/realtime/ingest` | Ingest raw tick (internal/webhook) |

---

## Testing

```bash
# All 231 tests
cd backend
.venv\Scripts\activate
python -m pytest backend/tests/ ../tests/ -v

# Just parity tests (critical — must always pass)
python -m pytest backend/tests/test_decision_parity.py -v

# Just risk tests
python -m pytest backend/tests/test_risk.py backend/tests/test_paper_risk_gating.py -v

# Just broker tests
python -m pytest ../tests/test_broker.py -v

# With coverage
python -m pytest backend/tests/ ../tests/ --cov=backend/app --cov-report=term-missing
```

**Test suite breakdown:**

| File | Tests | What it covers |
|------|-------|----------------|
| `test_decision_parity.py` | 8 | Python↔TS parity, determinism |
| `test_risk.py` | 18 | All 6 risk rules, env scoping |
| `test_paper_matching.py` | 12 | Limit order fills, slippage |
| `test_paper_positions.py` | 14 | WAP accounting, P&L |
| `test_paper_risk_gating.py` | 6 | Risk gate on paper orders |
| `test_backtest_causality.py` | 3 | No lookahead, cost deduction |
| `test_backtest_metrics.py` | 15 | Sharpe, Calmar, drawdown |
| `test_strategies_framework.py` | 5 | Strategy delegation, signals |
| `test_quant_regimes.py` | 8 | Regime thresholds |
| `test_ml_regime.py` | 14 | Probabilistic regime output |
| `test_ml_drift.py` | 14 | PSI drift detection |
| `test_ml_calibration.py` | 12 | Platt/isotonic calibration |
| `test_similarity.py` | 20 | Vector store, patterns |
| `test_broker.py` | 28 | Order routing, risk gate, audit |
| *(+ 7 more files)* | 54 | Data quality, features, realtime, etc. |

---

## Database Migrations

Run in order against your PostgreSQL instance:

```bash
# Set connection string
export DATABASE_URL=postgresql://user:password@localhost:5432/aura

# Run migrations (example using psql)
psql $DATABASE_URL -f migrations/0002_aura_core.sql
psql $DATABASE_URL -f migrations/0003_phase1_risk_events.sql
psql $DATABASE_URL -f migrations/0004_market_data.sql
psql $DATABASE_URL -f migrations/0005_backtest_runs.sql
psql $DATABASE_URL -f migrations/0006_paper_engine.sql
```

> App runs without a database in simulator/paper mode. DB is required only for persistent signal history, backtest run storage, and audit logs.

---

## Risk Engine — Rules & Safety

Every order (paper or live) passes through `snapshot_risk()` before execution:

```python
snap = snapshot_risk(
    kill_switch=store.kill_switch,   # Manual emergency stop
    book=book_state,                  # Current portfolio
    quotes=quotes,                    # Latest market data
    now=now_ms,
    last_tick=store.last_tick,        # For staleness check
    ops_window=ops_window,            # For throttle check
    static_ip_ok=req.staticIpOk,     # IP whitelist (LIVE only)
    env=req.env,                      # "PAPER" | "LIVE"
)
if not snap.canTrade:
    # Order BLOCKED — reason in snap.breaches
```

| Rule | Threshold | Env |
|------|-----------|-----|
| Kill switch | Manual | ALL |
| Daily loss | −2% of ₹10,00,000 (−₹20,000) | ALL |
| Exposure cap | 80% NAV | ALL |
| Max positions | 5 open at once | ALL |
| Stale data | >5 seconds | ALL |
| Ops throttle | 9 orders/second | ALL |
| Static IP | Must be whitelisted | LIVE only |

---

## Live Trading — How to Enable

> ⚠️ **Do NOT enable until you have verified all prerequisites.**

**Prerequisites:**
1. Angel One trading account with API access
2. Static IP address (Angel One requirement — whitelist with broker)
3. OpenAlgo instance running and connected to Angel One
4. `OPENALGO_API_KEY` obtained from your OpenAlgo dashboard

**Steps:**
```bash
# 1. Set environment variables
export OPENALGO_API_KEY=your_key_here
export OPENALGO_BASE_URL=http://your-openalgo-instance:5000
export AURA_LIVE_TRADING=1       # ← This is the final gate

# 2. Restart backend
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# 3. Verify status
curl http://127.0.0.1:8000/api/broker/status
# Should show: liveEnabled=true, apiKeyConfigured=true

# 4. Test with a small paper order FIRST
# Only then switch to env=LIVE on real orders
```

**Order request for live:**
```json
{
  "symbol": "NIFTY25JUNFUT",
  "exchange": "NFO",
  "action": "BUY",
  "quantity": 50,
  "orderType": "MARKET",
  "productType": "MIS",
  "env": "LIVE",
  "staticIpOk": true
}
```

---

## Architecture Decisions

### Single Source of Truth — Strategy Logic
`quant/base_strategy.py` strategies delegate `evaluate()` to `engines/decision/strategies.py`. There is **exactly one** implementation of `ma_cross`, `vwap_rsi`, and `orb`. The backtester, Strategy Lab API, and live dashboard all call the same code path. Divergence is structurally impossible.

### Risk Gate — Two Layers
1. **Order Router** (`order_router.py`): First gate. Calls `snapshot_risk()` before routing to paper or live.
2. **Paper Book** (`book.py`): Second gate. `place_order()` independently calls `get_risk_snapshot()`. Belt and suspenders.

### Parity Testing
`test_decision_parity.py` uses deterministic seeded simulation to compare Python output against canonical TypeScript snapshots. These 8 tests are the single most important tests in the suite — if they fail, the Python engine has diverged from the TS source.

### Live Trading Disabled by Default
`AURA_LIVE_TRADING=1` is an explicit environment variable. Without it, the broker client raises `BrokerDisabledError` on all live methods. This cannot be bypassed by the order router — it is checked at the client level.

---

## Branches

Both branches are identical as of `4636e1b`:

```
main:   4636e1b  (fix: resolve 4 critical review issues)
master: 4636e1b  (same)
```

**Use `main` as the working branch.** `master` is kept in sync.

---

## Contributing / Development Notes

- All new strategy logic goes into `engines/decision/strategies.py` — never duplicate in `quant/`
- All new risk rules go into `engines/risk/risk.py` — `snapshot_risk()` is the single enforcement point
- Any new order path (new broker, new env) must call `_run_risk_gate()` before routing
- Run full test suite before every commit: `python -m pytest backend/tests/ tests/ -q`
- `test_decision_parity.py` must always be green — never skip it

---

## License

Private repository. All rights reserved — BCASTUDENT28.
