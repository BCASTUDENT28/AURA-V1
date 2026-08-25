"""
backend/app/db/models.py

SQLAlchemy model for risk_events table.
This is the ONLY table added in Phase 1 (migration 0003).

IMPORTANT: write_risk_event() is ONLY called from the risk engine internally.
           No API route exposes a way for the frontend to insert a row directly.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy engine — only created if DATABASE_URL is set
_engine = None
_SessionLocal = None
_risk_events_table = None


def _get_engine():
    global _engine, _SessionLocal, _risk_events_table
    if _engine is not None:
        return _engine

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return None

    try:
        from sqlalchemy import (
            BigInteger,
            Column,
            MetaData,
            String,
            Table,
            Text,
            create_engine,
            text,
        )
        from sqlalchemy.orm import sessionmaker

        _engine = create_engine(db_url, pool_pre_ping=True)

        meta = MetaData()
        _risk_events_table = Table(
            "risk_events",
            meta,
            Column("id", BigInteger, primary_key=True, autoincrement=True),
            Column("rule_name", String, nullable=False),
            Column("severity", String, nullable=False),
            Column("outcome", String, nullable=False),
            Column("signal_id", String, nullable=True),
            Column("details", Text, nullable=True),  # stored as JSON string
            Column("created_at", String, server_default="NOW()"),
        )

        _SessionLocal = sessionmaker(bind=_engine)
        return _engine

    except Exception as exc:
        logger.warning("DB engine creation failed: %s", exc)
        return None


def write_risk_event(
    rule_name: str,
    severity: str,
    outcome: str,
    signal_id: Optional[str],
    details: dict,
) -> None:
    """
    Insert a row into risk_events.
    Called ONLY by the risk engine — never directly by an API route.
    Silently no-ops when DATABASE_URL is not set (unit tests).
    """
    engine = _get_engine()
    if engine is None:
        logger.debug(
            "risk_event (no-op, no DB): rule=%s severity=%s outcome=%s",
            rule_name, severity, outcome,
        )
        return

    try:
        from sqlalchemy import insert
        with engine.begin() as conn:
            conn.execute(
                _risk_events_table.insert().values(
                    rule_name=rule_name,
                    severity=severity,
                    outcome=outcome,
                    signal_id=signal_id,
                    details=json.dumps(details),
                )
            )
    except Exception as exc:
        logger.error("write_risk_event failed: %s", exc)
