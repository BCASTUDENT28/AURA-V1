"""
backend/tests/test_cost.py

Cost engine tests.
Each case is hand-calculated using the known DEFAULT_COST rates.

DEFAULT_COST:
  brokerageRate    = 0.0003  (capped at ₹20)
  brokerageCap     = 20.00
  sttDelivery      = 0.001   (both buy+sell)
  sttIntradaySell  = 0.00025 (sell only)
  stampDelivery    = 0.00015 (buy only)
  stampIntraday    = 0.00003 (buy only)
  exchangeRate     = 0.0000297
  sebiRate         = 0.000001
  gstRate          = 0.18    (on brokerage+exchange+sebi)
  slippageBps      = 2       → 0.0002
"""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.engines.cost.cost import DEFAULT_COST, estimate_costs

TOLS = 1e-6


def close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLS or (a != 0 and abs(a - b) / abs(a) <= TOLS)


# ---------------------------------------------------------------------------
# Hand-calculated reference values for turnover = ₹100,000
# ---------------------------------------------------------------------------

TURNOVER = 100_000.0


def hand_calc(turnover, side, product):
    c = DEFAULT_COST
    brokerage = min(turnover * c["brokerageRate"], c["brokerageCap"])
    if product == "DELIVERY":
        stt = turnover * c["sttDelivery"]
    elif side == "SELL":
        stt = turnover * c["sttIntradaySell"]
    else:
        stt = 0.0
    if side == "BUY":
        stamp = turnover * (c["stampDelivery"] if product == "DELIVERY" else c["stampIntraday"])
    else:
        stamp = 0.0
    exchange = turnover * c["exchangeRate"]
    sebi = turnover * c["sebiRate"]
    gst = (brokerage + exchange + sebi) * c["gstRate"]
    slippage = turnover * (c["slippageBps"] / 10_000)
    total = brokerage + stt + stamp + exchange + sebi + gst + slippage
    return {
        "brokerage": brokerage, "stt": stt, "stamp": stamp,
        "exchange": exchange, "sebi": sebi, "gst": gst,
        "slippage": slippage, "total": total,
    }


# ---------------------------------------------------------------------------
# Intraday equity BUY (₹100k)
# ---------------------------------------------------------------------------

@pytest.fixture(name="intraday_buy")
def _intraday_buy():
    return estimate_costs(TURNOVER, "BUY", "INTRADAY", "equity")


def test_intraday_buy_brokerage(intraday_buy):
    expected = min(TURNOVER * 0.0003, 20.0)
    assert close(intraday_buy.brokerage, expected)


def test_intraday_buy_stt_zero(intraday_buy):
    """Intraday buy has no STT."""
    assert intraday_buy.stt == 0.0


def test_intraday_buy_stamp(intraday_buy):
    expected = TURNOVER * 0.00003
    assert close(intraday_buy.stamp, expected)


def test_intraday_buy_exchange(intraday_buy):
    expected = TURNOVER * 0.0000297
    assert close(intraday_buy.exchange, expected)


def test_intraday_buy_sebi(intraday_buy):
    expected = TURNOVER * 0.000001
    assert close(intraday_buy.sebi, expected)


def test_intraday_buy_gst(intraday_buy):
    brokerage = min(TURNOVER * 0.0003, 20.0)
    exchange = TURNOVER * 0.0000297
    sebi = TURNOVER * 0.000001
    expected = (brokerage + exchange + sebi) * 0.18
    assert close(intraday_buy.gst, expected)


def test_intraday_buy_slippage(intraday_buy):
    expected = TURNOVER * 2 / 10_000
    assert close(intraday_buy.slippage, expected)


def test_intraday_buy_total(intraday_buy):
    expected = hand_calc(TURNOVER, "BUY", "INTRADAY")["total"]
    assert close(intraday_buy.total, expected)


# ---------------------------------------------------------------------------
# Intraday equity SELL (₹100k)
# ---------------------------------------------------------------------------

@pytest.fixture(name="intraday_sell")
def _intraday_sell():
    return estimate_costs(TURNOVER, "SELL", "INTRADAY", "equity")


def test_intraday_sell_stt(intraday_sell):
    expected = TURNOVER * 0.00025
    assert close(intraday_sell.stt, expected)


def test_intraday_sell_no_stamp(intraday_sell):
    assert intraday_sell.stamp == 0.0


def test_intraday_sell_total(intraday_sell):
    expected = hand_calc(TURNOVER, "SELL", "INTRADAY")["total"]
    assert close(intraday_sell.total, expected)


# ---------------------------------------------------------------------------
# Delivery equity BUY (₹100k)
# ---------------------------------------------------------------------------

@pytest.fixture(name="delivery_buy")
def _delivery_buy():
    return estimate_costs(TURNOVER, "BUY", "DELIVERY", "equity")


def test_delivery_buy_stt(delivery_buy):
    expected = TURNOVER * 0.001
    assert close(delivery_buy.stt, expected)


def test_delivery_buy_stamp(delivery_buy):
    expected = TURNOVER * 0.00015
    assert close(delivery_buy.stamp, expected)


def test_delivery_buy_total(delivery_buy):
    expected = hand_calc(TURNOVER, "BUY", "DELIVERY")["total"]
    assert close(delivery_buy.total, expected)


# ---------------------------------------------------------------------------
# Delivery equity SELL (₹100k)
# ---------------------------------------------------------------------------

@pytest.fixture(name="delivery_sell")
def _delivery_sell():
    return estimate_costs(TURNOVER, "SELL", "DELIVERY", "equity")


def test_delivery_sell_stt(delivery_sell):
    expected = TURNOVER * 0.001
    assert close(delivery_sell.stt, expected)


def test_delivery_sell_no_stamp(delivery_sell):
    assert delivery_sell.stamp == 0.0


def test_delivery_sell_total(delivery_sell):
    expected = hand_calc(TURNOVER, "SELL", "DELIVERY")["total"]
    assert close(delivery_sell.total, expected)


# ---------------------------------------------------------------------------
# Brokerage cap — large turnover (₹1M) should cap at ₹20
# ---------------------------------------------------------------------------

def test_brokerage_cap():
    result = estimate_costs(1_000_000.0, "BUY", "INTRADAY", "equity")
    assert result.brokerage == 20.0, f"Expected cap at ₹20, got {result.brokerage}"


# ---------------------------------------------------------------------------
# Total is sum of components
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("side,product", [
    ("BUY", "INTRADAY"),
    ("SELL", "INTRADAY"),
    ("BUY", "DELIVERY"),
    ("SELL", "DELIVERY"),
])
def test_total_is_sum(side, product):
    r = estimate_costs(TURNOVER, side, product, "equity")
    computed_total = r.brokerage + r.stt + r.stamp + r.exchange + r.sebi + r.gst + r.slippage
    assert close(r.total, computed_total), (
        f"total={r.total} != sum of components={computed_total}"
    )


# ---------------------------------------------------------------------------
# Zero turnover edge case
# ---------------------------------------------------------------------------

def test_zero_turnover():
    r = estimate_costs(0.0, "BUY", "INTRADAY", "equity")
    assert r.total == 0.0
    assert r.brokerage == 0.0
