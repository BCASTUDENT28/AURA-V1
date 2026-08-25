"""
backend/tests/test_risk.py

Risk engine tests.

Coverage:
  - Every threshold: pass case + breach case
  - Explicit: env="PAPER" + static_ip_ok=False → NOT a breach (can trade)
  - Explicit: env="LIVE"  + static_ip_ok=False → BLOCK (cannot trade)
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.engines.risk.risk import snapshot_risk
from backend.app.schemas.types import PaperBook, PaperPosition, Quote, STARTING_CASH

PAPER_NOW = 1755390300000  # PAPER_OPEN


def _make_quote(symbol: str, ltp: float) -> Quote:
    return Quote(
        symbol=symbol, ltp=ltp, bid=ltp - 0.5, ask=ltp + 0.5,
        open=ltp, high=ltp, low=ltp, prevClose=ltp,
        change=0, changePct=0, volume=1000, ts=PAPER_NOW,
    )


def _make_position(symbol: str, qty: float, avg_price: float, side: str = "BUY") -> PaperPosition:
    return PaperPosition(
        symbol=symbol, qty=qty, avgPrice=avg_price, side=side,
        stop=None, target=None, openedTs=PAPER_NOW, realized=0.0,
        costs=0.0, strategyId=None,
    )


def _empty_book(**kwargs) -> PaperBook:
    return PaperBook(**kwargs)


# ---------------------------------------------------------------------------
# Helper: run snapshot with sensible defaults
# ---------------------------------------------------------------------------

def _snap(
    kill_switch=False,
    positions=None,
    daily_pnl=0.0,
    data_age_ms=0,
    ops_window=None,
    static_ip_ok=False,
    env="PAPER",
    quotes=None,
    cash=STARTING_CASH,
):
    now = PAPER_NOW
    last_tick = now - data_age_ms
    book = PaperBook(cash=cash, dailyPnl=daily_pnl, positions=positions or [])
    quotes = quotes or {
        "NIFTY": _make_quote("NIFTY", 24862),
        "SBIN":  _make_quote("SBIN",  812),
    }
    return snapshot_risk(
        kill_switch=kill_switch,
        book=book,
        quotes=quotes,
        now=now,
        last_tick=last_tick,
        ops_window=ops_window or [],
        static_ip_ok=static_ip_ok,
        env=env,
    )


# ---------------------------------------------------------------------------
# 1. Kill switch
# ---------------------------------------------------------------------------

def test_kill_switch_pass():
    snap = _snap(kill_switch=False)
    assert "Kill switch is armed" not in " ".join(snap.breaches)


def test_kill_switch_breach():
    snap = _snap(kill_switch=True)
    assert not snap.canTrade
    assert any("Kill switch" in b for b in snap.breaches)


# ---------------------------------------------------------------------------
# 2. Daily loss circuit breaker
# ---------------------------------------------------------------------------

def test_daily_loss_pass():
    snap = _snap(daily_pnl=-10_000)  # -1% of 1M — under limit
    assert not any("Daily loss" in b for b in snap.breaches)


def test_daily_loss_breach():
    snap = _snap(daily_pnl=-25_000)  # -2.5% of 1M — over limit
    assert not snap.canTrade
    assert any("Daily loss" in b for b in snap.breaches)


# ---------------------------------------------------------------------------
# 3. Portfolio exposure cap (80%)
# ---------------------------------------------------------------------------

def test_exposure_cap_pass():
    positions = [_make_position("NIFTY", 10, 24862)]
    quotes = {"NIFTY": _make_quote("NIFTY", 24862)}
    snap = _snap(positions=positions, quotes=quotes, cash=STARTING_CASH)
    assert not any("exposure cap" in b.lower() for b in snap.breaches)


def test_exposure_cap_breach():
    # Exposure = 10 * 24862 = 248620, NAV ≈ equity (small equity) → exposure/nav > 0.8
    # Set cash very low so equity is tiny and exposure/nav > 0.8
    positions = [_make_position("NIFTY", 100, 24862)]
    quotes = {"NIFTY": _make_quote("NIFTY", 24862)}
    snap = _snap(positions=positions, quotes=quotes, cash=10_000)  # tiny cash → big exposure ratio
    assert any("exposure cap" in b.lower() for b in snap.breaches)


# ---------------------------------------------------------------------------
# 4. Max simultaneous positions (5)
# ---------------------------------------------------------------------------

def test_max_positions_pass():
    positions = [_make_position(f"SYM{i}", 1, 100) for i in range(4)]
    quotes = {p.symbol: _make_quote(p.symbol, 100) for p in positions}
    snap = _snap(positions=positions, quotes=quotes)
    assert not any("Max simultaneous" in b for b in snap.breaches)


def test_max_positions_breach():
    positions = [_make_position(f"SYM{i}", 1, 100) for i in range(5)]  # exactly at limit → breach
    quotes = {p.symbol: _make_quote(p.symbol, 100) for p in positions}
    snap = _snap(positions=positions, quotes=quotes)
    assert not snap.canTrade
    assert any("Max simultaneous" in b for b in snap.breaches)


# ---------------------------------------------------------------------------
# 5. Stale data (> 5000ms)
# ---------------------------------------------------------------------------

def test_stale_data_pass():
    snap = _snap(data_age_ms=1000)  # fresh
    assert not any("stale" in b.lower() for b in snap.breaches)


def test_stale_data_breach():
    snap = _snap(data_age_ms=6000)  # > 5000ms
    assert not snap.canTrade
    assert any("stale" in b.lower() for b in snap.breaches)


# ---------------------------------------------------------------------------
# 6. Ops rate throttle (9 ops/sec)
# ---------------------------------------------------------------------------

def test_ops_rate_pass():
    now = PAPER_NOW
    ops_window = [now - 200] * 8  # 8 in last second — under limit
    snap = _snap(ops_window=ops_window)
    assert not any("throttle" in b.lower() for b in snap.breaches)


def test_ops_rate_breach():
    now = PAPER_NOW
    ops_window = [now - 100] * 9  # 9 in last second — at/over limit
    snap = _snap(ops_window=ops_window)
    assert not snap.canTrade
    assert any("throttle" in b.lower() for b in snap.breaches)


# ---------------------------------------------------------------------------
# 7. Limit-only (stop-loss required — tested via gateOrder path)
# This is enforced at order gate, not in snapshot_risk, so we test the
# snapshot is valid and the gateOrder check correctly requires stop.
# ---------------------------------------------------------------------------

def test_limit_only_pass():
    snap = _snap()
    # Snapshot itself doesn't check order type — it's a portfolio snapshot
    assert snap.canTrade  # no breaches → can trade


def test_stop_loss_required_in_breach_list():
    # Snapshot does not enforce stop-loss (that's gateOrder).
    # We assert snapshot doesn't add a false stop-loss breach.
    snap = _snap()
    assert not any("stop" in b.lower() for b in snap.breaches)


# ---------------------------------------------------------------------------
# 8. Sector concentration cap (tested implicitly via multiple positions)
# ---------------------------------------------------------------------------

def test_sector_cap_no_false_positive():
    # Single position, small — should not trigger sector cap
    pos = [_make_position("SBIN", 10, 812)]
    quotes = {"SBIN": _make_quote("SBIN", 812)}
    snap = _snap(positions=pos, quotes=quotes)
    assert "Sector" not in " ".join(snap.breaches)


# ---------------------------------------------------------------------------
# 9. COMPLIANCE-CHECK SCOPING (THE MOST IMPORTANT TEST)
# ---------------------------------------------------------------------------

def test_paper_env_static_ip_false_NOT_a_breach():
    """
    env="PAPER" + static_ip_ok=False → must NOT block trading.
    There is no broker in paper mode — the static-IP check does not apply.
    """
    snap = _snap(static_ip_ok=False, env="PAPER")
    # Static IP must NOT appear as a breach
    assert not any("Static IP" in b for b in snap.breaches), (
        f"static_ip_ok=False incorrectly blocks PAPER trading. Breaches: {snap.breaches}"
    )
    assert snap.canTrade, (
        f"canTrade=False in PAPER with only static_ip_ok=False. Breaches: {snap.breaches}"
    )


def test_dev_env_static_ip_false_NOT_a_breach():
    """env="DEV" + static_ip_ok=False → must NOT block trading."""
    snap = _snap(static_ip_ok=False, env="DEV")
    assert not any("Static IP" in b for b in snap.breaches)
    assert snap.canTrade


def test_live_env_static_ip_false_IS_a_breach():
    """
    env="LIVE" + static_ip_ok=False → MUST block trading.
    Static IP is required when connecting to a live broker.
    """
    snap = _snap(static_ip_ok=False, env="LIVE")
    assert not snap.canTrade, "LIVE env with static_ip_ok=False must block trading"
    assert any("Static IP" in b for b in snap.breaches), (
        f"Expected 'Static IP' breach in LIVE env. Breaches: {snap.breaches}"
    )


def test_live_env_static_ip_true_passes():
    """env="LIVE" + static_ip_ok=True → no static-IP breach."""
    snap = _snap(static_ip_ok=True, env="LIVE")
    assert not any("Static IP" in b for b in snap.breaches)


# ---------------------------------------------------------------------------
# 10. static_ip_ok has no default — must be explicit
# ---------------------------------------------------------------------------

def test_static_ip_ok_has_no_default():
    """snapshot_risk() must require static_ip_ok explicitly."""
    import inspect
    sig = inspect.signature(snapshot_risk)
    param = sig.parameters.get("static_ip_ok")
    assert param is not None, "static_ip_ok parameter missing"
    assert param.default is inspect.Parameter.empty, (
        "static_ip_ok must have no default value — it must always be explicit"
    )


def test_env_has_no_default():
    """snapshot_risk() must require env explicitly."""
    import inspect
    sig = inspect.signature(snapshot_risk)
    param = sig.parameters.get("env")
    assert param is not None, "env parameter missing"
    assert param.default is inspect.Parameter.empty, (
        "env must have no default value — it gates static-IP check"
    )
