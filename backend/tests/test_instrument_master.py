"""
backend/tests/test_instrument_master.py

Tests for Canonical Instrument Master and Broker Mappings.
Verifies:
- Broker neutrality: Internal IDs are strictly decoupled from broker tokens
- Token resolution for Angel One and Groww
- Filter capabilities (by sector, segment, active state)
- Lot and tick constraints
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.data.master import get_instrument_master
from backend.app.schemas.market_data import BrokerMapping, InstrumentRecord


@pytest.fixture(name="master")
def _master_fixture():
    return get_instrument_master()


def test_master_has_core_instruments(master):
    """Core instruments must be registered and active."""
    for sym in ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN"]:
        inst = master.get_by_symbol(sym)
        assert inst is not None, f"Missing instrument: {sym}"
        assert inst.isActive is True
        assert inst.lotSize >= 1
        assert inst.tickSize == 0.05
        assert inst.basePrice > 0


def test_internal_id_format(master):
    """Internal IDs must follow the canonical format 'EXCHANGE:SYMBOL'."""
    reliance = master.get_by_symbol("RELIANCE")
    assert reliance.id == "NSE:RELIANCE"

    nifty = master.get_by_symbol("NIFTY")
    assert nifty.id == "NSE:NIFTY50"


def test_broker_token_mapping_angel_one(master):
    """Verify Angel One tokens are mapped without polluting canonical properties."""
    token = master.get_broker_token("RELIANCE", "ANGEL_ONE")
    assert token == "2885"

    token_hdfc = master.get_broker_token("HDFCBANK", "ANGEL_ONE")
    assert token_hdfc == "1333"

    token_nifty = master.get_broker_token("NIFTY", "ANGEL_ONE")
    assert token_nifty == "99926000"


def test_broker_token_mapping_groww(master):
    """Verify Groww tokens are mapped correctly."""
    token = master.get_broker_token("RELIANCE", "GROWW")
    assert token == "NSE_RELIANCE"

    token_nifty = master.get_broker_token("NIFTY", "GROWW")
    assert token_nifty == "INDEX_NIFTY50"


def test_reverse_token_lookup(master):
    """Given an Angel One token, resolve back to the canonical instrument."""
    inst = master.resolve_broker_token("ANGEL_ONE", "2885")
    assert inst is not None
    assert inst.symbol == "RELIANCE"
    assert inst.id == "NSE:RELIANCE"


def test_filter_by_sector(master):
    """Filter universe by sector."""
    it_stocks = master.list_all(sector="IT")
    assert len(it_stocks) >= 2
    symbols = [s.symbol for s in it_stocks]
    assert "TCS" in symbols
    assert "INFY" in symbols
    assert "RELIANCE" not in symbols


def test_filter_by_segment(master):
    """Filter universe by segment."""
    indices = master.list_all(segment="INDEX")
    assert len(indices) >= 2
    symbols = [s.symbol for s in indices]
    assert "NIFTY" in symbols
    assert "BANKNIFTY" in symbols
    assert "RELIANCE" not in symbols


def test_dynamic_instrument_registration(master):
    """New instruments can be registered dynamically."""
    new_inst = InstrumentRecord(
        id="NSE:TATAPOWER",
        symbol="TATAPOWER",
        name="Tata Power Company Ltd",
        exchange="NSE",
        segment="EQUITY",
        sector="Energy",
        kind="equity",
        lotSize=1,
        tickSize=0.05,
        basePrice=412.0,
        avgVolume=8.5e6,
        brokerMappings=[
            BrokerMapping(broker="ANGEL_ONE", brokerSymbol="TATAPOWER-EQ", brokerToken="3426"),
        ],
    )
    master.register(new_inst)

    fetched = master.get_by_symbol("TATAPOWER")
    assert fetched is not None
    assert fetched.name == "Tata Power Company Ltd"
    assert master.get_broker_token("TATAPOWER", "ANGEL_ONE") == "3426"
