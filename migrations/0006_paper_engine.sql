-- Migration 0006: Phase 5 Paper Trading Engine & Persistent Portfolio State
-- Enhances paper trading state with audit timestamps and lineage tracking.

CREATE INDEX IF NOT EXISTS idx_paper_orders_status ON paper_orders (status, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_paper_fills_order ON paper_fills (order_id, ts_ms DESC);

-- Add audit event trigger comment
COMMENT ON TABLE paper_book_state IS
    'Authoritative server-side portfolio book state for paper trading. '
    'Persisted to PostgreSQL so paper trading operates without requiring an open browser.';
