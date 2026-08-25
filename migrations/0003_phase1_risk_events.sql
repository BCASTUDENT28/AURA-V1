-- Migration 0003: Phase 1 Risk Events table
-- This is the ONLY schema change for Phase 1.
-- The row may ONLY be written by the backend risk engine itself,
-- internally, as a side effect of evaluating a signal.
-- There must be no API route that lets the frontend or any client
-- insert a risk_events row directly.

CREATE TABLE IF NOT EXISTS risk_events (
    id          BIGSERIAL    PRIMARY KEY,
    rule_name   TEXT         NOT NULL,
    severity    TEXT         NOT NULL,
    outcome     TEXT         NOT NULL,
    signal_id   TEXT,                        -- nullable: not all events have an associated signal
    details     JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Index for querying recent events by rule
CREATE INDEX IF NOT EXISTS risk_events_rule_name_idx
    ON risk_events (rule_name, created_at DESC);

-- Index for querying events by signal (when signal_id is set)
CREATE INDEX IF NOT EXISTS risk_events_signal_id_idx
    ON risk_events (signal_id)
    WHERE signal_id IS NOT NULL;

COMMENT ON TABLE risk_events IS
    'Risk rule evaluation log. Written only by the backend risk engine. '
    'No external API may insert rows directly. Phase 1: PAPER env only.';
