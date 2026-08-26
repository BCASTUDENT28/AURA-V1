"""
tests/test_broker.py

Phase 9 — Broker Integration tests.
Tests order router, validation, audit log, and live-gate enforcement.
All live-broker network calls are tested in disabled mode (no real HTTP).
"""

from __future__ import annotations

import os
import pytest

from backend.app.broker.openalgo_client import (
    OpenAlgoClient,
    BrokerDisabledError,
    BrokerOrder,
)
from backend.app.broker.order_router import (
    OrderRequest,
    route_order,
    get_audit_log,
    _AUDIT_LOG,
)


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _make_request(**overrides) -> OrderRequest:
    base = dict(
        symbol="NIFTY25JUNFUT",
        exchange="NFO",
        action="BUY",
        quantity=50,
        orderType="MARKET",
        productType="MIS",
        price=0.0,
        triggerPrice=0.0,
        strategyTag="AURA_TEST",
        env="PAPER",
        staticIpOk=False,
    )
    base.update(overrides)
    return OrderRequest(**base)


def _clear_audit():
    _AUDIT_LOG.clear()


# ─────────────────────────────────────────────────────────
# Live-gate enforcement
# ─────────────────────────────────────────────────────────

class TestLiveGate:

    def test_place_order_raises_when_not_enabled(self):
        """AURA_LIVE_TRADING not set → BrokerDisabledError."""
        os.environ.pop("AURA_LIVE_TRADING", None)
        client = OpenAlgoClient()
        order = BrokerOrder(
            symbol="NIFTY25JUNFUT", exchange="NFO",
            action="BUY", quantity=50,
            orderType="MARKET", productType="MIS",
        )
        with pytest.raises(BrokerDisabledError):
            client.place_order(order)

    def test_get_positions_raises_when_not_enabled(self):
        os.environ.pop("AURA_LIVE_TRADING", None)
        client = OpenAlgoClient()
        with pytest.raises(BrokerDisabledError):
            client.get_positions()

    def test_get_funds_raises_when_not_enabled(self):
        os.environ.pop("AURA_LIVE_TRADING", None)
        client = OpenAlgoClient()
        with pytest.raises(BrokerDisabledError):
            client.get_funds()

    def test_cancel_order_raises_when_not_enabled(self):
        os.environ.pop("AURA_LIVE_TRADING", None)
        client = OpenAlgoClient()
        with pytest.raises(BrokerDisabledError):
            client.cancel_order("12345")


# ─────────────────────────────────────────────────────────
# Order Router — PAPER path
# ─────────────────────────────────────────────────────────

class TestOrderRouterPaper:

    def setup_method(self):
        _clear_audit()
        os.environ.pop("AURA_LIVE_TRADING", None)

    def test_paper_order_returns_simulated(self):
        req = _make_request(env="PAPER")
        entry = route_order(req)
        assert entry.status == "SIMULATED"
        assert entry.routedTo == "PAPER"

    def test_paper_order_has_audit_entry(self):
        req = _make_request(env="PAPER")
        route_order(req)
        log = get_audit_log()
        assert len(log) >= 1
        assert log[-1].status == "SIMULATED"

    def test_paper_order_id_has_paper_prefix(self):
        req = _make_request(env="PAPER")
        entry = route_order(req)
        assert entry.orderId is not None
        assert entry.orderId.startswith("PAPER-")

    def test_paper_order_has_latency(self):
        req = _make_request(env="PAPER")
        entry = route_order(req)
        assert entry.latencyMs is not None
        assert entry.latencyMs >= 0.0

    def test_paper_order_symbol_preserved(self):
        req = _make_request(symbol="BANKNIFTY25JUN55000CE", env="PAPER")
        entry = route_order(req)
        assert entry.symbol == "BANKNIFTY25JUN55000CE"

    def test_paper_buy_and_sell(self):
        for action in ["BUY", "SELL"]:
            req = _make_request(action=action, env="PAPER")
            entry = route_order(req)
            assert entry.status == "SIMULATED"
            assert entry.action == action


# ─────────────────────────────────────────────────────────
# Order Router — Validation / Rejection
# ─────────────────────────────────────────────────────────

class TestOrderRouterValidation:

    def setup_method(self):
        _clear_audit()
        os.environ.pop("AURA_LIVE_TRADING", None)

    def test_invalid_action_rejected(self):
        req = _make_request(action="HOLD")
        entry = route_order(req)
        assert entry.status == "REJECTED"
        assert entry.routedTo == "REJECTED"
        assert entry.rejectionReason is not None

    def test_zero_quantity_rejected(self):
        req = _make_request(quantity=0)
        entry = route_order(req)
        assert entry.status == "REJECTED"

    def test_negative_quantity_rejected(self):
        req = _make_request(quantity=-10)
        entry = route_order(req)
        assert entry.status == "REJECTED"

    def test_quantity_over_max_rejected(self):
        req = _make_request(quantity=99999)
        entry = route_order(req)
        assert entry.status == "REJECTED"

    def test_invalid_order_type_rejected(self):
        req = _make_request(orderType="STOP_LOSS_MARKET")
        entry = route_order(req)
        assert entry.status == "REJECTED"

    def test_invalid_exchange_rejected(self):
        req = _make_request(exchange="NASDAQ")
        entry = route_order(req)
        assert entry.status == "REJECTED"

    def test_live_without_static_ip_rejected(self):
        req = _make_request(env="LIVE", staticIpOk=False)
        entry = route_order(req)
        assert entry.status == "REJECTED"
        assert "staticIpOk" in (entry.rejectionReason or "")

    def test_live_without_env_var_rejected(self):
        """Even with staticIpOk=True, no env var → rejected."""
        os.environ.pop("AURA_LIVE_TRADING", None)
        req = _make_request(env="LIVE", staticIpOk=True)
        entry = route_order(req)
        assert entry.status == "REJECTED"

    def test_rejected_entry_in_audit_log(self):
        req = _make_request(action="INVALID")
        route_order(req)
        log = get_audit_log()
        assert any(e.status == "REJECTED" for e in log)


# ─────────────────────────────────────────────────────────
# Audit Log
# ─────────────────────────────────────────────────────────

class TestAuditLog:

    def setup_method(self):
        _clear_audit()
        os.environ.pop("AURA_LIVE_TRADING", None)

    def test_audit_log_grows_with_orders(self):
        for _ in range(5):
            route_order(_make_request())
        assert len(get_audit_log()) == 5

    def test_audit_entry_has_request_id(self):
        route_order(_make_request())
        entry = get_audit_log()[0]
        assert isinstance(entry.requestId, str)
        assert len(entry.requestId) > 0

    def test_audit_entry_has_timestamp(self):
        route_order(_make_request())
        entry = get_audit_log()[0]
        assert entry.timestamp > 0

    def test_audit_log_bounded(self):
        """Audit log should not grow unbounded beyond MAX_AUDIT_ENTRIES."""
        from backend.app.broker.order_router import MAX_AUDIT_ENTRIES
        # Submit more than max
        for i in range(5):
            route_order(_make_request(symbol=f"SYM{i}"))
        assert len(get_audit_log()) <= MAX_AUDIT_ENTRIES


# ─────────────────────────────────────────────────────────
# Broker Status (no live required)
# ─────────────────────────────────────────────────────────

class TestBrokerStatus:

    def setup_method(self):
        os.environ.pop("AURA_LIVE_TRADING", None)
        os.environ.pop("OPENALGO_API_KEY", None)

    def test_status_live_disabled_by_default(self):
        client = OpenAlgoClient()
        status = client.status()
        assert status.liveEnabled is False

    def test_status_api_key_not_configured(self):
        client = OpenAlgoClient()
        status = client.status()
        assert status.apiKeyConfigured is False

    def test_status_reports_base_url(self):
        client = OpenAlgoClient()
        status = client.status()
        assert isinstance(status.baseUrl, str)
        assert len(status.baseUrl) > 0

    def test_status_live_enabled_when_env_set(self):
        os.environ["AURA_LIVE_TRADING"] = "1"
        try:
            client = OpenAlgoClient()
            status = client.status()
            assert status.liveEnabled is True
        finally:
            os.environ.pop("AURA_LIVE_TRADING", None)

    def test_status_api_key_configured_when_set(self):
        os.environ["OPENALGO_API_KEY"] = "test_key_xyz"
        try:
            client = OpenAlgoClient()
            status = client.status()
            assert status.apiKeyConfigured is True
        finally:
            os.environ.pop("OPENALGO_API_KEY", None)
