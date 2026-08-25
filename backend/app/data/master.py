"""
backend/app/data/master.py

Canonical Instrument Master for AURA AI.
Maintains canonical instrument definitions decoupled from broker-specific tokens.
Maps internal IDs (e.g. 'NSE:RELIANCE') to Angel One and Groww representations.
"""

from __future__ import annotations

from typing import Optional
from backend.app.schemas.market_data import (
    BrokerMapping,
    InstrumentRecord,
)

# ---------------------------------------------------------------------------
# Canonical Instrument Seed Master with Pre-wired Broker Token Mappings
# ---------------------------------------------------------------------------

_SEED_INSTRUMENTS: list[InstrumentRecord] = [
    InstrumentRecord(
        id="NSE:NIFTY50",
        symbol="NIFTY",
        name="Nifty 50",
        exchange="NSE",
        segment="INDEX",
        sector="Index",
        kind="index",
        lotSize=1,
        tickSize=0.05,
        basePrice=24862.0,
        avgVolume=2.4e8,
        brokerMappings=[
            BrokerMapping(broker="ANGEL_ONE", brokerSymbol="NIFTY", brokerToken="99926000", segment="NSE_INDEX"),
            BrokerMapping(broker="GROWW", brokerSymbol="NIFTY50", brokerToken="INDEX_NIFTY50", segment="INDEX"),
        ],
    ),
    InstrumentRecord(
        id="NSE:BANKNIFTY",
        symbol="BANKNIFTY",
        name="Nifty Bank",
        exchange="NSE",
        segment="INDEX",
        sector="Index",
        kind="index",
        lotSize=1,
        tickSize=0.05,
        basePrice=51240.0,
        avgVolume=8.1e7,
        brokerMappings=[
            BrokerMapping(broker="ANGEL_ONE", brokerSymbol="BANKNIFTY", brokerToken="99926009", segment="NSE_INDEX"),
            BrokerMapping(broker="GROWW", brokerSymbol="BANKNIFTY", brokerToken="INDEX_BANKNIFTY", segment="INDEX"),
        ],
    ),
    InstrumentRecord(
        id="NSE:RELIANCE",
        symbol="RELIANCE",
        name="Reliance Industries",
        exchange="NSE",
        segment="EQUITY",
        sector="Energy",
        kind="equity",
        lotSize=1,
        tickSize=0.05,
        basePrice=1478.0,
        avgVolume=6.2e6,
        brokerMappings=[
            BrokerMapping(broker="ANGEL_ONE", brokerSymbol="RELIANCE-EQ", brokerToken="2885", segment="NSE_CM"),
            BrokerMapping(broker="GROWW", brokerSymbol="RELIANCE", brokerToken="NSE_RELIANCE", segment="EQUITY"),
        ],
    ),
    InstrumentRecord(
        id="NSE:TCS",
        symbol="TCS",
        name="Tata Consultancy Services",
        exchange="NSE",
        segment="EQUITY",
        sector="IT",
        kind="equity",
        lotSize=1,
        tickSize=0.05,
        basePrice=4124.0,
        avgVolume=2.1e6,
        brokerMappings=[
            BrokerMapping(broker="ANGEL_ONE", brokerSymbol="TCS-EQ", brokerToken="11536", segment="NSE_CM"),
            BrokerMapping(broker="GROWW", brokerSymbol="TCS", brokerToken="NSE_TCS", segment="EQUITY"),
        ],
    ),
    InstrumentRecord(
        id="NSE:HDFCBANK",
        symbol="HDFCBANK",
        name="HDFC Bank",
        exchange="NSE",
        segment="EQUITY",
        sector="Banks",
        kind="equity",
        lotSize=1,
        tickSize=0.05,
        basePrice=1682.0,
        avgVolume=1.4e7,
        brokerMappings=[
            BrokerMapping(broker="ANGEL_ONE", brokerSymbol="HDFCBANK-EQ", brokerToken="1333", segment="NSE_CM"),
            BrokerMapping(broker="GROWW", brokerSymbol="HDFCBANK", brokerToken="NSE_HDFCBANK", segment="EQUITY"),
        ],
    ),
    InstrumentRecord(
        id="NSE:INFY",
        symbol="INFY",
        name="Infosys",
        exchange="NSE",
        segment="EQUITY",
        sector="IT",
        kind="equity",
        lotSize=1,
        tickSize=0.05,
        basePrice=1786.0,
        avgVolume=6.8e6,
        brokerMappings=[
            BrokerMapping(broker="ANGEL_ONE", brokerSymbol="INFY-EQ", brokerToken="1594", segment="NSE_CM"),
            BrokerMapping(broker="GROWW", brokerSymbol="INFY", brokerToken="NSE_INFY", segment="EQUITY"),
        ],
    ),
    InstrumentRecord(
        id="NSE:ICICIBANK",
        symbol="ICICIBANK",
        name="ICICI Bank",
        exchange="NSE",
        segment="EQUITY",
        sector="Banks",
        kind="equity",
        lotSize=1,
        tickSize=0.05,
        basePrice=1284.0,
        avgVolume=1.1e7,
        brokerMappings=[
            BrokerMapping(broker="ANGEL_ONE", brokerSymbol="ICICIBANK-EQ", brokerToken="4963", segment="NSE_CM"),
            BrokerMapping(broker="GROWW", brokerSymbol="ICICIBANK", brokerToken="NSE_ICICIBANK", segment="EQUITY"),
        ],
    ),
    InstrumentRecord(
        id="NSE:SBIN",
        symbol="SBIN",
        name="State Bank of India",
        exchange="NSE",
        segment="EQUITY",
        sector="Banks",
        kind="equity",
        lotSize=1,
        tickSize=0.05,
        basePrice=812.0,
        avgVolume=1.5e7,
        brokerMappings=[
            BrokerMapping(broker="ANGEL_ONE", brokerSymbol="SBIN-EQ", brokerToken="3045", segment="NSE_CM"),
            BrokerMapping(broker="GROWW", brokerSymbol="SBIN", brokerToken="NSE_SBIN", segment="EQUITY"),
        ],
    ),
    InstrumentRecord(
        id="NSE:BHARTIARTL",
        symbol="BHARTIARTL",
        name="Bharti Airtel",
        exchange="NSE",
        segment="EQUITY",
        sector="Telecom",
        kind="equity",
        lotSize=1,
        tickSize=0.05,
        basePrice=1648.0,
        avgVolume=5.4e6,
        brokerMappings=[
            BrokerMapping(broker="ANGEL_ONE", brokerSymbol="BHARTIARTL-EQ", brokerToken="10604", segment="NSE_CM"),
            BrokerMapping(broker="GROWW", brokerSymbol="BHARTIARTL", brokerToken="NSE_BHARTIARTL", segment="EQUITY"),
        ],
    ),
    InstrumentRecord(
        id="NSE:ITC",
        symbol="ITC",
        name="ITC Limited",
        exchange="NSE",
        segment="EQUITY",
        sector="FMCG",
        kind="equity",
        lotSize=1,
        tickSize=0.05,
        basePrice=492.0,
        avgVolume=1.2e7,
        brokerMappings=[
            BrokerMapping(broker="ANGEL_ONE", brokerSymbol="ITC-EQ", brokerToken="1660", segment="NSE_CM"),
            BrokerMapping(broker="GROWW", brokerSymbol="ITC", brokerToken="NSE_ITC", segment="EQUITY"),
        ],
    ),
]


class InstrumentMasterRegistry:
    def __init__(self, seed: list[InstrumentRecord] = None):
        self._by_id: dict[str, InstrumentRecord] = {}
        self._by_symbol: dict[str, InstrumentRecord] = {}
        self._broker_lookup: dict[tuple[str, str], InstrumentRecord] = {}

        from backend.app.data.simulator import INSTRUMENTS
        # Seed explicitly configured instruments first
        for inst in seed or _SEED_INSTRUMENTS:
            self.register(inst)
        # Register any remaining instruments from simulator universe
        for sim_inst in INSTRUMENTS:
            if sim_inst.symbol not in self._by_symbol:
                self.register(
                    InstrumentRecord(
                        id=f"NSE:{sim_inst.symbol}",
                        symbol=sim_inst.symbol,
                        name=sim_inst.name,
                        exchange="NSE",
                        segment="INDEX" if sim_inst.kind == "index" else "EQUITY",
                        sector=sim_inst.sector,
                        kind=sim_inst.kind,
                        lotSize=sim_inst.lot,
                        tickSize=sim_inst.tick,
                        basePrice=sim_inst.base,
                        avgVolume=sim_inst.avgVolume,
                        brokerMappings=[
                            BrokerMapping(broker="ANGEL_ONE", brokerSymbol=f"{sim_inst.symbol}-EQ", brokerToken=f"TKN_{sim_inst.symbol}"),
                            BrokerMapping(broker="GROWW", brokerSymbol=sim_inst.symbol, brokerToken=f"GROWW_{sim_inst.symbol}"),
                        ],
                    )
                )

    def register(self, inst: InstrumentRecord) -> None:
        self._by_id[inst.id] = inst
        self._by_symbol[inst.symbol] = inst
        for mapping in inst.brokerMappings:
            self._broker_lookup[(mapping.broker, mapping.brokerToken)] = inst

    def get_by_id(self, internal_id: str) -> Optional[InstrumentRecord]:
        return self._by_id.get(internal_id)

    def get_by_symbol(self, symbol: str) -> Optional[InstrumentRecord]:
        return self._by_symbol.get(symbol.upper())

    def resolve_broker_token(self, broker: str, token: str) -> Optional[InstrumentRecord]:
        return self._broker_lookup.get((broker, token))

    def get_broker_token(self, symbol: str, broker: str) -> Optional[str]:
        inst = self.get_by_symbol(symbol)
        if not inst:
            return None
        for m in inst.brokerMappings:
            if m.broker == broker and m.isValid:
                return m.brokerToken
        return None

    def list_all(
        self,
        sector: Optional[str] = None,
        segment: Optional[str] = None,
        active_only: bool = True,
    ) -> list[InstrumentRecord]:
        out = list(self._by_id.values())
        if active_only:
            out = [i for i in out if i.isActive]
        if sector:
            out = [i for i in out if i.sector.lower() == sector.lower()]
        if segment:
            out = [i for i in out if i.segment.lower() == segment.lower()]
        return out


# Global singleton registry
_master_registry = InstrumentMasterRegistry()


def get_instrument_master() -> InstrumentMasterRegistry:
    return _master_registry
