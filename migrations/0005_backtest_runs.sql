-- Migration 0005: Phase 4 Backtest Runs, Trades, and Walk-Forward Results
-- Stores persistent research experiments and individual trade execution records.

CREATE TABLE IF NOT EXISTS backtest_runs (
    id                  TEXT PRIMARY KEY,              -- e.g. 'run-ma_cross-NIFTY-1D-20240821'
    strategy_id         TEXT NOT NULL,
    strategy_version    TEXT NOT NULL DEFAULT 'v1',
    symbol              TEXT NOT NULL,
    timeframe           TEXT NOT NULL DEFAULT '1D',
    start_time_ms       BIGINT NOT NULL,
    end_time_ms         BIGINT NOT NULL,
    initial_capital     DOUBLE PRECISION NOT NULL DEFAULT 1000000.0,
    final_equity        DOUBLE PRECISION NOT NULL,
    net_pnl             DOUBLE PRECISION NOT NULL,
    net_pnl_pct         DOUBLE PRECISION NOT NULL,
    total_trades        INTEGER NOT NULL DEFAULT 0,
    winning_trades      INTEGER NOT NULL DEFAULT 0,
    losing_trades       INTEGER NOT NULL DEFAULT 0,
    win_rate            DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    profit_factor       DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    sharpe_ratio        DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    sortino_ratio       DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    max_drawdown_pct    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    total_costs         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    avg_r_multiple      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    expectancy          DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    params_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    dataset_version_id  TEXT,
    feature_version_id  TEXT DEFAULT 'feat-v1',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bt_runs_strat_sym ON backtest_runs (strategy_id, symbol, created_at DESC);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    trade_num           INTEGER NOT NULL,
    symbol              TEXT NOT NULL,
    side                TEXT NOT NULL,                 -- 'BUY', 'SELL'
    qty                 DOUBLE PRECISION NOT NULL,
    entry_ts            BIGINT NOT NULL,
    entry_px            DOUBLE PRECISION NOT NULL,
    exit_ts             BIGINT NOT NULL,
    exit_px             DOUBLE PRECISION NOT NULL,
    gross_pnl           DOUBLE PRECISION NOT NULL,
    net_pnl             DOUBLE PRECISION NOT NULL,
    total_costs         DOUBLE PRECISION NOT NULL,
    r_multiple          DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    exit_reason         TEXT NOT NULL DEFAULT 'SIGNAL',-- 'STOP_LOSS', 'TAKE_PROFIT', 'SIGNAL', 'SESSION_CLOSE'
    duration_bars       INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_bt_trades_run ON backtest_trades (run_id, trade_num);
