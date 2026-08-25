-- AURA production core (paper-only). Unowned single-desk rows.
-- Reset archives a session; nothing is bulk-deleted.

create table if not exists aura_lineage (
  id text primary key,
  kind text not null,
  name text not null,
  version text not null,
  status text not null default 'active',
  notes text not null default '',
  created_at timestamptz not null default now()
);

create table if not exists aura_cost_config (
  id text primary key,
  version text not null,
  brokerage_rate double precision not null,
  brokerage_cap double precision not null,
  stt_delivery double precision not null,
  stt_intraday_sell double precision not null,
  stamp_delivery double precision not null,
  stamp_intraday double precision not null,
  exchange_rate double precision not null,
  sebi_rate double precision not null,
  gst_rate double precision not null,
  slippage_bps double precision not null,
  source_note text not null,
  verified boolean not null default false,
  is_current boolean not null default true,
  effective_from timestamptz not null default now()
);

create table if not exists paper_session (
  id text primary key,
  started_at timestamptz not null default now(),
  closed_at timestamptz,
  starting_cash double precision not null,
  status text not null default 'open',
  env text not null default 'PAPER',
  data_source text not null default 'SIMULATOR'
);

create table if not exists paper_book_state (
  session_id text primary key references paper_session(id),
  cash double precision not null,
  realized double precision not null default 0,
  daily_pnl double precision not null default 0,
  session_start_nav double precision not null,
  kill_switch boolean not null default false,
  book_json text not null,
  learnings_json text not null default '[]',
  updated_at timestamptz not null default now()
);

create table if not exists paper_orders (
  id text primary key,
  session_id text not null references paper_session(id),
  ts_ms bigint not null,
  symbol text not null,
  side text not null,
  type text not null,
  qty double precision not null,
  limit_price double precision not null,
  status text not null,
  fill_price double precision,
  costs_json text,
  reject_reason text,
  strategy_id text,
  stop_px double precision,
  target_px double precision,
  lineage_json text
);

create index if not exists paper_orders_session_idx on paper_orders (session_id, ts_ms desc);

create table if not exists paper_fills (
  id text primary key,
  session_id text not null references paper_session(id),
  order_id text not null,
  ts_ms bigint not null,
  symbol text not null,
  side text not null,
  qty double precision not null,
  price double precision not null,
  costs_json text not null
);

create index if not exists paper_fills_session_idx on paper_fills (session_id, ts_ms desc);

create table if not exists memory_learning (
  id text primary key,
  session_id text not null references paper_session(id),
  ts_ms bigint not null,
  kind text not null,
  setup text not null,
  strategy_id text not null,
  strategy_version_id text not null,
  model_version_id text not null,
  feature_version_id text not null,
  dataset_version_id text not null,
  regime text not null,
  symbol text not null,
  evidence text not null,
  sample_size integer not null default 1,
  min_sample_required integer not null default 5,
  confidence double precision not null,
  expires_ts bigint not null,
  r_multiple double precision
);

create index if not exists memory_learning_session_idx on memory_learning (session_id, ts_ms desc);

create table if not exists signal_lineage (
  id text primary key,
  ts_ms bigint not null,
  symbol text not null,
  action text not null,
  strategy_version_id text not null,
  model_version_id text not null,
  feature_version_id text not null,
  dataset_version_id text not null,
  cost_version_id text not null,
  payload_json text not null
);

insert into aura_lineage (id, kind, name, version, status, notes) values
  ('strategy:ma_cross@v1', 'strategy', 'MA crossover', 'v1', 'active', 'Rules V1. Keep as research prototype. Not a production alpha.'),
  ('strategy:vwap_rsi@v1', 'strategy', 'VWAP + RSI', 'v1', 'active', 'Rules V1. Continuation only with volume confirmation.'),
  ('strategy:orb@v1', 'strategy', 'Opening range breakout', 'v1', 'active', 'Rules V1. Skips wide opening ranges. Intrabar assumptions need audit.'),
  ('model:regime-rules-v1', 'model', 'Regime rules', 'regime-rules-v1', 'active', 'Heuristics, not a trained model. Placeholder for Regime ML.'),
  ('feature:feat-v1', 'feature', 'Feature pack', 'feat-v1', 'active', 'SMA/EMA/RSI/MACD/ATR/ADX/VWAP/BB/RV/volumeZ. Version in DB, not a string constant forever.'),
  ('dataset:sim-in-eq-20240821', 'dataset', 'Simulated Indian cash', 'sim-in-eq-20240821', 'research', 'Deterministic synthetic OHLC. Not NSE. Do not treat as evidence of edge.'),
  ('cost:in-cash-2026-unverified-v1', 'cost', 'IN cash cost model', 'in-cash-2026-unverified-v1', 'unverified', 'Discount-broker style defaults. Verify against official broker/exchange schedules before trusting P&L.')
on conflict (id) do nothing;

insert into aura_cost_config (
  id, version, brokerage_rate, brokerage_cap, stt_delivery, stt_intraday_sell,
  stamp_delivery, stamp_intraday, exchange_rate, sebi_rate, gst_rate, slippage_bps,
  source_note, verified, is_current
) values (
  'cost:in-cash-2026-unverified-v1',
  'in-cash-2026-unverified-v1',
  0.0003, 20, 0.001, 0.00025, 0.00015, 0.00003, 0.0000297, 0.000001, 0.18, 2,
  'Unverified 2026 discount-broker defaults. Confirm against current broker, NSE, BSE, STT, stamp and SEBI schedules. Do not treat net P&L as official.',
  false,
  true
) on conflict (id) do nothing;
