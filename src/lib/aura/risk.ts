import { getInstrument } from "./instruments";
import type {
  Decision,
  PaperPosition,
  Quote,
  RiskLimits,
  RiskSnapshot,
} from "./types";
import { STARTING_CASH } from "./types";

export const DEFAULT_LIMITS: RiskLimits = {
  maxPositionPct: 0.1,
  maxDailyLossPct: 0.02,
  maxExposurePct: 0.8,
  maxPositions: 5,
  maxSectorPct: 0.35,
  opsPerSec: 9,
  stopRequired: true,
  limitOnly: true,
  dataFreshMs: 5000,
};

export function snapshotRisk(args: {
  killSwitch: boolean;
  cash: number;
  positions: PaperPosition[];
  quotes: Record<string, Quote>;
  dailyPnl: number;
  now: number;
  lastTick: number;
  opsWindow: number[];
  staticIpOk?: boolean;
}): RiskSnapshot {
  const { positions, quotes, cash, dailyPnl, now, lastTick, opsWindow } = args;
  const equity = cash + positions.reduce((a, p) => {
    const ltp = quotes[p.symbol]?.ltp ?? p.avgPrice;
    const dir = p.side === "BUY" ? 1 : -1;
    return a + dir * (ltp - p.avgPrice) * p.qty + p.avgPrice * p.qty * (p.side === "SELL" ? 0 : 1);
  }, 0);
  const nav = Math.max(equity, 1);
  const exposure = positions.reduce((a, p) => a + Math.abs(p.qty * (quotes[p.symbol]?.ltp ?? p.avgPrice)), 0);
  const breaches: string[] = [];
  if (args.killSwitch) breaches.push("Kill switch is armed — all orders blocked.");
  if (dailyPnl / STARTING_CASH <= -DEFAULT_LIMITS.maxDailyLossPct) {
    breaches.push("Daily loss circuit breaker.");
  }
  if (exposure / nav > DEFAULT_LIMITS.maxExposurePct) breaches.push("Portfolio exposure cap.");
  if (positions.length >= DEFAULT_LIMITS.maxPositions) breaches.push("Max simultaneous positions.");
  const dataAge = now - lastTick;
  if (dataAge > DEFAULT_LIMITS.dataFreshMs) breaches.push("Market data is stale.");
  const recent = opsWindow.filter((t) => now - t < 1000).length;
  if (recent >= DEFAULT_LIMITS.opsPerSec) breaches.push("9 orders/sec throttle (Angel One cap).");
  if (!args.staticIpOk) breaches.push("Static IP not verified — live path sealed.");

  return {
    killSwitch: args.killSwitch,
    dailyPnl,
    dailyPnlPct: dailyPnl / STARTING_CASH,
    exposurePct: exposure / nav,
    openPositions: positions.length,
    dataAgeMs: dataAge,
    opsWindow,
    staticIpOk: args.staticIpOk ?? false,
    env: "PAPER",
    livePathSealed: true,
    dataSource: "SIMULATOR",
    breaches,
    canTrade: breaches.length === 0,
  };
}

export function gateOrder(args: {
  symbol: string;
  side: "BUY" | "SELL";
  qty: number;
  limitPrice: number;
  stop: number | null;
  type: "LIMIT" | "MARKET" | "IOC";
  quotes: Record<string, Quote>;
  positions: PaperPosition[];
  cash: number;
  risk: RiskSnapshot;
  existingOpenOrder?: boolean;
}): { ok: true } | { ok: false; reasons: string[] } {
  const reasons: string[] = [...args.risk.breaches];
  if (args.type !== "LIMIT") reasons.push("Algo path is limit-orders only (NSE: no market/IOC).");
  if (DEFAULT_LIMITS.stopRequired && (args.stop == null || args.stop <= 0)) {
    reasons.push("Stop-loss is required.");
  }
  const inst = getInstrument(args.symbol);
  const notional = args.qty * args.limitPrice;
  const nav = STARTING_CASH;
  if (notional / nav > DEFAULT_LIMITS.maxPositionPct) {
    reasons.push(`Position > ${(DEFAULT_LIMITS.maxPositionPct * 100).toFixed(0)}% of book.`);
  }
  if (args.side === "BUY" && notional > args.cash) reasons.push("Insufficient cash.");
  if (args.qty <= 0) reasons.push("Quantity must be positive.");
  if (args.existingOpenOrder) reasons.push("Duplicate working order on this symbol.");
  const q = args.quotes[args.symbol];
  if (!q) reasons.push("No quote.");
  const sectorNotional = args.positions
    .filter((p) => getInstrument(p.symbol).sector === inst.sector)
    .reduce((a, p) => a + Math.abs(p.qty * (args.quotes[p.symbol]?.ltp ?? p.avgPrice)), 0);
  if ((sectorNotional + notional) / nav > DEFAULT_LIMITS.maxSectorPct) {
    reasons.push("Sector concentration cap.");
  }
  if (reasons.length) return { ok: false, reasons };
  return { ok: true };
}

export function applyRiskToDecision(d: Decision, risk: RiskSnapshot): Decision {
  if (risk.canTrade) return d;
  return {
    ...d,
    action: "SKIP",
    risk: "BLOCKED",
    confidence: Math.min(d.confidence, 0.2),
    riskReasons: risk.breaches,
    contradictions: [
      ...d.contradictions,
      { kind: "contradict" as const, text: "Risk engine veto — SKIP. AI cannot override." },
    ],
  };
}
