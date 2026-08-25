"""
backend/app/engines/risk/risk.py

Port of src/lib/aura/risk.ts
snapshot_risk() — authoritative Python risk engine.

COMPLIANCE-CHECK SCOPING:
- static_ip_ok has NO default — must be passed explicitly on every call.
- env has NO default — gates when the static-IP check applies.
- When env == "LIVE": static_ip_ok=False → BLOCK
- When env == "PAPER" or "DEV": static_ip_ok=False → NOT a breach
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.app.schemas.types import (
    PaperBook,
    PaperPosition,
    Quote,
    RiskLimits,
    RiskSnapshot,
    STARTING_CASH,
)

logger = logging.getLogger(__name__)

DEFAULT_LIMITS = RiskLimits(
    maxPositionPct=0.1,
    maxDailyLossPct=0.02,
    maxExposurePct=0.8,
    maxPositions=5,
    maxSectorPct=0.35,
    opsPerSec=9,
    stopRequired=True,
    limitOnly=True,
    dataFreshMs=5000,
)


def _write_risk_event(
    rule_name: str,
    severity: str,
    outcome: str,
    signal_id: Optional[str],
    details: dict,
) -> None:
    """
    Write a risk_events row to the database.
    Only called internally by snapshot_risk() — no external API exposes this write.
    Falls back to a log warning when DATABASE_URL is not configured.
    """
    try:
        from backend.app.db.models import write_risk_event  # type: ignore
        write_risk_event(
            rule_name=rule_name,
            severity=severity,
            outcome=outcome,
            signal_id=signal_id,
            details=details,
        )
    except ImportError:
        # DB not configured — log and continue (unit tests run without a real DB)
        logger.warning(
            "risk_event [%s] severity=%s outcome=%s signal_id=%s details=%s",
            rule_name, severity, outcome, signal_id, details,
        )
    except Exception as exc:
        logger.error("Failed to write risk_event %s: %s", rule_name, exc)


def snapshot_risk(
    kill_switch: bool,
    book: PaperBook,
    quotes: dict[str, Quote],
    now: int,
    last_tick: int,
    ops_window: list[int],
    static_ip_ok: bool,   # NO DEFAULT — must be explicit on every call
    env: str,             # NO DEFAULT — "PAPER" | "LIVE" | "DEV"
) -> RiskSnapshot:
    """
    Compute a RiskSnapshot.

    Compliance-check scoping:
    - static_ip_ok=False + env="LIVE"  → BLOCK (live path sealed)
    - static_ip_ok=False + env="PAPER" → NOT a breach (no broker attached)
    - static_ip_ok=False + env="DEV"   → NOT a breach
    """
    positions = book.positions
    cash = book.cash
    daily_pnl = book.dailyPnl

    # NAV calculation
    equity = cash
    for p in positions:
        ltp = quotes[p.symbol].ltp if p.symbol in quotes else p.avgPrice
        dir_ = 1 if p.side == "BUY" else -1
        equity += dir_ * (ltp - p.avgPrice) * p.qty + p.avgPrice * p.qty * (1 if p.side != "SELL" else 0)
    nav = max(equity, 1.0)

    # Exposure
    exposure = sum(
        abs(p.qty * (quotes[p.symbol].ltp if p.symbol in quotes else p.avgPrice))
        for p in positions
    )

    breaches: list[str] = []

    # --- Kill switch ---
    if kill_switch:
        breaches.append("Kill switch is armed — all orders blocked.")
        _write_risk_event("kill_switch", "CRITICAL", "BLOCK", None, {"kill_switch": True})

    # --- Daily loss circuit breaker ---
    if daily_pnl / STARTING_CASH <= -DEFAULT_LIMITS.maxDailyLossPct:
        breaches.append("Daily loss circuit breaker.")
        _write_risk_event("daily_loss", "HIGH", "BLOCK", None, {
            "dailyPnl": daily_pnl, "threshold": -DEFAULT_LIMITS.maxDailyLossPct * STARTING_CASH
        })

    # --- Portfolio exposure cap ---
    if exposure / nav > DEFAULT_LIMITS.maxExposurePct:
        breaches.append("Portfolio exposure cap.")
        _write_risk_event("exposure_cap", "HIGH", "BLOCK", None, {
            "exposurePct": exposure / nav, "limit": DEFAULT_LIMITS.maxExposurePct
        })

    # --- Max simultaneous positions ---
    if len(positions) >= DEFAULT_LIMITS.maxPositions:
        breaches.append("Max simultaneous positions.")
        _write_risk_event("max_positions", "MEDIUM", "BLOCK", None, {
            "positions": len(positions), "limit": DEFAULT_LIMITS.maxPositions
        })

    # --- Stale data ---
    data_age = now - last_tick
    if data_age > DEFAULT_LIMITS.dataFreshMs:
        breaches.append("Market data is stale.")
        _write_risk_event("stale_data", "MEDIUM", "WARN", None, {
            "dataAgeMs": data_age, "limit": DEFAULT_LIMITS.dataFreshMs
        })

    # --- Ops rate throttle ---
    recent = sum(1 for t in ops_window if now - t < 1000)
    if recent >= DEFAULT_LIMITS.opsPerSec:
        breaches.append("9 orders/sec throttle (Angel One cap).")
        _write_risk_event("ops_rate", "HIGH", "BLOCK", None, {
            "recentOps": recent, "limit": DEFAULT_LIMITS.opsPerSec
        })

    # --- Static IP check — ONLY when env == "LIVE" ---
    if env == "LIVE" and not static_ip_ok:
        breaches.append("Static IP not verified — live path sealed.")
        _write_risk_event("static_ip", "CRITICAL", "BLOCK", None, {
            "staticIpOk": False, "env": env
        })
    # env == "PAPER" or "DEV": static_ip_ok=False is NOT a breach (no broker attached)

    return RiskSnapshot(
        killSwitch=kill_switch,
        dailyPnl=daily_pnl,
        dailyPnlPct=daily_pnl / STARTING_CASH,
        exposurePct=exposure / nav,
        openPositions=len(positions),
        dataAgeMs=data_age,
        opsWindow=ops_window,
        staticIpOk=static_ip_ok,
        env=env,
        livePathSealed=True,
        dataSource="SIMULATOR",
        breaches=breaches,
        canTrade=len(breaches) == 0,
    )
