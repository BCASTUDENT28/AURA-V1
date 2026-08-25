-- Migration 0004: Phase 2 Persistent Research Data & Instrument Master
-- Establishes the canonical instrument master, broker token mappings,
-- corporate action logs, multi-timeframe OHLCV store, dataset versions, and data quality reports.

-- 1. Canonical Instrument Master (Broker-Neutral)
CREATE TABLE IF NOT EXISTS instruments (
    id              TEXT PRIMARY KEY,              -- e.g. 'NSE:NIFTY50', 'NSE:RELIANCE'
    symbol          TEXT NOT NULL UNIQUE,          -- e.g. 'NIFTY', 'RELIANCE'
    name            TEXT NOT NULL,
    exchange        TEXT NOT NULL DEFAULT 'NSE',   -- 'NSE', 'BSE'
    segment         TEXT NOT NULL DEFAULT 'EQUITY',-- 'EQUITY', 'INDEX', 'FNO'
    sector          TEXT NOT NULL DEFAULT 'General',
    kind            TEXT NOT NULL DEFAULT 'equity',-- 'equity', 'index'
    lot_size        INTEGER NOT NULL DEFAULT 1,
    tick_size       DOUBLE PRECISION NOT NULL DEFAULT 0.05,
    base_price      DOUBLE PRECISION NOT NULL,
    avg_volume      DOUBLE PRECISION NOT NULL DEFAULT 1000000,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Instrument Broker Mappings (Decouples broker-specific tokens from strategies)
CREATE TABLE IF NOT EXISTS instrument_broker_mappings (
    id              BIGSERIAL PRIMARY KEY,
    instrument_id   TEXT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    broker          TEXT NOT NULL,                 -- 'ANGEL_ONE', 'GROWW', 'ZERODHA'
    broker_symbol   TEXT NOT NULL,                 -- e.g. 'RELIANCE-EQ'
    broker_token    TEXT NOT NULL,                 -- e.g. '2885' (Angel One token)
    segment         TEXT NOT NULL DEFAULT 'NSE_CM',
    is_valid        BOOLEAN NOT NULL DEFAULT TRUE,
    verified_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (instrument_id, broker)
);

CREATE INDEX IF NOT EXISTS idx_inst_broker_token ON instrument_broker_mappings (broker, broker_token);

-- 3. Corporate Actions (Splits, Bonuses, Dividends)
CREATE TABLE IF NOT EXISTS corporate_actions (
    id              BIGSERIAL PRIMARY KEY,
    instrument_id   TEXT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    action_type     TEXT NOT NULL,                 -- 'SPLIT', 'BONUS', 'DIVIDEND'
    ratio_from      DOUBLE PRECISION,              -- e.g. 1 (in 1:2 split)
    ratio_to        DOUBLE PRECISION,              -- e.g. 2
    dividend_amount DOUBLE PRECISION,
    ex_date         DATE NOT NULL,
    is_applied      BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_corp_actions_inst ON corporate_actions (instrument_id, ex_date DESC);

-- 4. Dataset Versions & Lineage
CREATE TABLE IF NOT EXISTS dataset_versions (
    id              TEXT PRIMARY KEY,              -- e.g. 'sim-in-eq-20240821', 'nse-hist-2024-v1'
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    source          TEXT NOT NULL,                 -- 'SIMULATOR', 'NSE_EOD', 'ANGEL_HISTORICAL'
    symbol_count    INTEGER NOT NULL DEFAULT 0,
    bar_count       BIGINT NOT NULL DEFAULT 0,
    start_time_ms   BIGINT NOT NULL,
    end_time_ms     BIGINT NOT NULL,
    checksum        TEXT NOT NULL,                 -- SHA256 checksum of normalized series
    is_immutable    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Data Quality Reports (Audit Trail)
CREATE TABLE IF NOT EXISTS data_quality_reports (
    id                  BIGSERIAL PRIMARY KEY,
    dataset_version_id  TEXT NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status              TEXT NOT NULL,             -- 'PASS', 'WARN', 'FAIL'
    missing_candles     INTEGER NOT NULL DEFAULT 0,
    duplicate_candles   INTEGER NOT NULL DEFAULT 0,
    outlier_ticks       INTEGER NOT NULL DEFAULT 0,
    corporate_actions_applied INTEGER NOT NULL DEFAULT 0,
    notes               TEXT NOT NULL DEFAULT '',
    metrics_json        JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_dq_report_dataset ON data_quality_reports (dataset_version_id, generated_at DESC);

-- 6. Persistent Daily OHLCV Candle Store
CREATE TABLE IF NOT EXISTS market_bars_daily (
    id                  BIGSERIAL PRIMARY KEY,
    instrument_id       TEXT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timestamp_ms        BIGINT NOT NULL,
    open                DOUBLE PRECISION NOT NULL,
    high                DOUBLE PRECISION NOT NULL,
    low                 DOUBLE PRECISION NOT NULL,
    close               DOUBLE PRECISION NOT NULL,
    volume              DOUBLE PRECISION NOT NULL,
    vwap                DOUBLE PRECISION,
    num_trades          INTEGER,
    is_adjusted         BOOLEAN NOT NULL DEFAULT TRUE,
    dataset_version_id  TEXT REFERENCES dataset_versions(id),
    UNIQUE (instrument_id, timestamp_ms, is_adjusted)
);

CREATE INDEX IF NOT EXISTS idx_bars_daily_inst_ts ON market_bars_daily (instrument_id, timestamp_ms DESC);

-- 7. Persistent Intraday OHLCV Candle Store (1m, 3m, 5m, 15m)
CREATE TABLE IF NOT EXISTS market_bars_intraday (
    id                  BIGSERIAL PRIMARY KEY,
    instrument_id       TEXT NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timeframe           TEXT NOT NULL DEFAULT '5m', -- '1m', '3m', '5m', '15m'
    timestamp_ms        BIGINT NOT NULL,
    open                DOUBLE PRECISION NOT NULL,
    high                DOUBLE PRECISION NOT NULL,
    low                 DOUBLE PRECISION NOT NULL,
    close               DOUBLE PRECISION NOT NULL,
    volume              DOUBLE PRECISION NOT NULL,
    vwap                DOUBLE PRECISION,
    is_adjusted         BOOLEAN NOT NULL DEFAULT TRUE,
    dataset_version_id  TEXT REFERENCES dataset_versions(id),
    UNIQUE (instrument_id, timeframe, timestamp_ms, is_adjusted)
);

CREATE INDEX IF NOT EXISTS idx_bars_intraday_lookup ON market_bars_intraday (instrument_id, timeframe, timestamp_ms DESC);
