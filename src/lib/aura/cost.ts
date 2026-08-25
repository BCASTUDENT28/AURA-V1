import type { CostBreakdown, InstrumentKind, OrderSide, ProductType } from "./types";
import { COST_VERSION } from "./types";

/**
 * Indian cash-market cost model (discount-broker style, 2026).
 * Configurable — not hardcoded into strategies.
 * Intraday equity is the default for the three short-horizon strategies.
 */
export interface CostConfig {
  brokerageRate: number;
  brokerageCap: number;
  sttDelivery: number;
  sttIntradaySell: number;
  stampDelivery: number;
  stampIntraday: number;
  exchangeRate: number;
  sebiRate: number;
  gstRate: number;
  slippageBps: number;
}

export const DEFAULT_COST: CostConfig = {
  brokerageRate: 0.0003,
  brokerageCap: 20,
  sttDelivery: 0.001,
  sttIntradaySell: 0.00025,
  stampDelivery: 0.00015,
  stampIntraday: 0.00003,
  exchangeRate: 0.0000297,
  sebiRate: 0.000001,
  gstRate: 0.18,
  slippageBps: 2,
};

export const COST_CONFIG_NOTE =
  "Unverified 2026 discount-broker defaults. Confirm against official schedules before trusting net P&L.";

export { COST_VERSION };

export function estimateCosts(args: {
  turnover: number;
  side: OrderSide;
  product: ProductType;
  kind: InstrumentKind;
  cfg?: CostConfig;
}): CostBreakdown {
  const cfg = args.cfg ?? DEFAULT_COST;
  const { turnover, side, product } = args;
  const brokerage = Math.min(turnover * cfg.brokerageRate, cfg.brokerageCap);
  const stt =
    product === "DELIVERY"
      ? turnover * cfg.sttDelivery
      : side === "SELL"
        ? turnover * cfg.sttIntradaySell
        : 0;
  const stamp =
    side === "BUY"
      ? turnover * (product === "DELIVERY" ? cfg.stampDelivery : cfg.stampIntraday)
      : 0;
  const exchange = turnover * cfg.exchangeRate;
  const sebi = turnover * cfg.sebiRate;
  const gst = (brokerage + exchange + sebi) * cfg.gstRate;
  const slippage = turnover * (cfg.slippageBps / 10000);
  const total = brokerage + stt + stamp + exchange + sebi + gst + slippage;
  return { brokerage, stt, stamp, exchange, sebi, gst, slippage, total };
}

export function roundTripCostPct(product: ProductType, kind: InstrumentKind, cfg = DEFAULT_COST): number {
  // Approximate one-way % * 2 using ₹1L notional so the cap binds realistically.
  const notional = 100_000;
  const buy = estimateCosts({ turnover: notional, side: "BUY", product, kind, cfg });
  const sell = estimateCosts({ turnover: notional, side: "SELL", product, kind, cfg });
  return (buy.total + sell.total) / notional;
}
