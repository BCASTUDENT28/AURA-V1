"""
backend/app/engines/cost/cost.py

Port of src/lib/aura/cost.ts
estimate_costs() — authoritative Python cost engine.
All rates match TypeScript DEFAULT_COST exactly.
"""

from __future__ import annotations

from backend.app.schemas.types import CostBreakdown

# ---------------------------------------------------------------------------
# Cost configuration (mirrors DEFAULT_COST in cost.ts)
# ---------------------------------------------------------------------------

DEFAULT_COST = {
    "brokerageRate": 0.0003,
    "brokerageCap": 20.0,
    "sttDelivery": 0.001,
    "sttIntradaySell": 0.00025,
    "stampDelivery": 0.00015,
    "stampIntraday": 0.00003,
    "exchangeRate": 0.0000297,
    "sebiRate": 0.000001,
    "gstRate": 0.18,
    "slippageBps": 2,
}

COST_CONFIG_NOTE = (
    "Unverified 2026 discount-broker defaults. "
    "Confirm against official schedules before trusting net P&L."
)


def estimate_costs(
    turnover: float,
    side: str,      # "BUY" | "SELL"
    product: str,   # "INTRADAY" | "DELIVERY"
    kind: str,      # "index" | "equity"  (kept for future FO differentiation)
    cfg: dict = None,
) -> CostBreakdown:
    """
    Compute Indian discount-broker cost breakdown for a given turnover.

    Parameter names match the TypeScript estimateCosts() args as closely
    as practical (side, product, kind).
    """
    c = cfg or DEFAULT_COST

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

    return CostBreakdown(
        brokerage=brokerage,
        stt=stt,
        stamp=stamp,
        exchange=exchange,
        sebi=sebi,
        gst=gst,
        slippage=slippage,
        total=total,
    )
