import { estimateCosts } from "./cost";
import { getInstrument } from "./instruments";
import { gateOrder, snapshotRisk } from "./risk";
import type {
  Learning,
  PaperFill,
  PaperOrder,
  PaperPosition,
  Quote,
  RiskSnapshot,
} from "./types";
import { STARTING_CASH } from "./types";

export interface PaperBook {
  cash: number;
  startingCash: number;
  positions: PaperPosition[];
  orders: PaperOrder[];
  fills: PaperFill[];
  dailyPnl: number;
  realized: number;
  sessionStartNav: number;
}

export function emptyBook(): PaperBook {
  return {
    cash: STARTING_CASH,
    startingCash: STARTING_CASH,
    positions: [],
    orders: [],
    fills: [],
    dailyPnl: 0,
    realized: 0,
    sessionStartNav: STARTING_CASH,
  };
}

export function navOf(book: PaperBook, quotes: Record<string, Quote>): number {
  let n = book.cash;
  for (const p of book.positions) {
    const ltp = quotes[p.symbol]?.ltp ?? p.avgPrice;
    if (p.side === "BUY") n += p.qty * ltp;
    else n += p.qty * (2 * p.avgPrice - ltp);
  }
  return n;
}

export function unrealizedOf(book: PaperBook, quotes: Record<string, Quote>): number {
  let u = 0;
  for (const p of book.positions) {
    const ltp = quotes[p.symbol]?.ltp ?? p.avgPrice;
    const dir = p.side === "BUY" ? 1 : -1;
    u += dir * (ltp - p.avgPrice) * p.qty;
  }
  return u;
}

let seq = 1;
const id = (p: string) => `${p}-${Date.now().toString(36)}-${seq++}`;

export function submitOrder(
  book: PaperBook,
  quotes: Record<string, Quote>,
  risk: RiskSnapshot,
  input: {
    symbol: string;
    side: "BUY" | "SELL";
    qty: number;
    limitPrice: number;
    stop: number | null;
    target: number | null;
    strategyId: string | null;
    now: number;
  },
): { book: PaperBook; order: PaperOrder; learning?: Learning } {
  const dup = book.orders.some((o) => o.symbol === input.symbol && o.status === "PENDING");
  const gate = gateOrder({
    symbol: input.symbol,
    side: input.side,
    qty: input.qty,
    limitPrice: input.limitPrice,
    stop: input.stop,
    type: "LIMIT",
    quotes,
    positions: book.positions,
    cash: book.cash,
    risk,
    existingOpenOrder: dup,
  });

  const order: PaperOrder = {
    id: id("ord"),
    ts: input.now,
    symbol: input.symbol,
    side: input.side,
    type: "LIMIT",
    qty: input.qty,
    limitPrice: input.limitPrice,
    status: "PENDING",
    fillPrice: null,
    costs: null,
    rejectReason: null,
    strategyId: input.strategyId,
    stop: input.stop,
    target: input.target,
  };

  if (!gate.ok) {
    order.status = "REJECTED";
    order.rejectReason = gate.reasons[0] ?? "Risk rejected";
    return { book: { ...book, orders: [order, ...book.orders] }, order };
  }

  const q = quotes[input.symbol]!;
  const marketable =
    input.side === "BUY" ? input.limitPrice >= q.ask - 1e-9 : input.limitPrice <= q.bid + 1e-9;
  if (!marketable) {
    return { book: { ...book, orders: [order, ...book.orders] }, order };
  }

  return fillOrder(book, order, q.ltp, input.now, quotes);
}

function fillOrder(
  book: PaperBook,
  order: PaperOrder,
  px: number,
  now: number,
  _quotes: Record<string, Quote>,
): { book: PaperBook; order: PaperOrder } {
  const inst = getInstrument(order.symbol);
  const costs = estimateCosts({
    turnover: px * order.qty,
    side: order.side,
    product: "INTRADAY",
    kind: inst.kind,
  });
  const fill: PaperFill = {
    id: id("f"),
    orderId: order.id,
    ts: now,
    symbol: order.symbol,
    side: order.side,
    qty: order.qty,
    price: px,
    costs,
  };
  const filled: PaperOrder = { ...order, status: "FILLED", fillPrice: px, costs };
  let cash = book.cash - costs.total;
  let realized = book.realized;
  const positions = book.positions.map((p) => ({ ...p }));
  const idx = positions.findIndex((p) => p.symbol === order.symbol);
  const existing = idx >= 0 ? positions[idx]! : null;

  if (!existing) {
    if (order.side === "BUY") cash -= px * order.qty;
    positions.push({
      symbol: order.symbol,
      qty: order.qty,
      avgPrice: px,
      side: order.side,
      stop: order.stop,
      target: order.target,
      openedTs: now,
      realized: 0,
      costs: costs.total,
      strategyId: order.strategyId,
    });
  } else if (existing.side === order.side) {
    if (order.side === "BUY") cash -= px * order.qty;
    const tot = existing.qty + order.qty;
    existing.avgPrice = (existing.avgPrice * existing.qty + px * order.qty) / tot;
    existing.qty = tot;
    existing.costs += costs.total;
  } else {
    // closing / flipping
    const closeQty = Math.min(existing.qty, order.qty);
    const dir = existing.side === "BUY" ? 1 : -1;
    const pnl = dir * (px - existing.avgPrice) * closeQty;
    if (existing.side === "BUY") cash += px * closeQty;
    else cash += existing.avgPrice * closeQty + dir * (px - existing.avgPrice) * closeQty;
    existing.qty -= closeQty;
    existing.realized += pnl;
    realized += pnl;
    if (existing.qty === 0) positions.splice(idx, 1);
    const remain = order.qty - closeQty;
    if (remain > 0) {
      if (order.side === "BUY") cash -= px * remain;
      positions.push({
        symbol: order.symbol,
        qty: remain,
        avgPrice: px,
        side: order.side,
        stop: order.stop,
        target: order.target,
        openedTs: now,
        realized: 0,
        costs: costs.total,
        strategyId: order.strategyId,
      });
    }
  }

  const next: PaperBook = {
    ...book,
    cash,
    realized,
    positions,
    orders: [filled, ...book.orders.filter((o) => o.id !== order.id)],
    fills: [fill, ...book.fills],
  };
  return { book: next, order: filled };
}

export function matchWorking(book: PaperBook, quotes: Record<string, Quote>, now: number): PaperBook {
  let next = book;
  for (const o of book.orders.filter((x) => x.status === "PENDING")) {
    const q = quotes[o.symbol];
    if (!q) continue;
    const hit = o.side === "BUY" ? q.ltp <= o.limitPrice : q.ltp >= o.limitPrice;
    if (hit) {
      const r = fillOrder(next, o, o.limitPrice, now, quotes);
      next = r.book;
    }
  }
  return next;
}

export function checkStops(book: PaperBook, quotes: Record<string, Quote>, now: number, risk: RiskSnapshot): PaperBook {
  let next = book;
  for (const p of [...book.positions]) {
    const q = quotes[p.symbol];
    if (!q) continue;
    const hitStop =
      p.stop != null && ((p.side === "BUY" && q.ltp <= p.stop) || (p.side === "SELL" && q.ltp >= p.stop));
    const hitTgt =
      p.target != null && ((p.side === "BUY" && q.ltp >= p.target) || (p.side === "SELL" && q.ltp <= p.target));
    if (hitStop || hitTgt) {
      const r = submitOrder(next, quotes, { ...risk, canTrade: true, breaches: [] }, {
        symbol: p.symbol,
        side: p.side === "BUY" ? "SELL" : "BUY",
        qty: p.qty,
        limitPrice: q.ltp,
        stop: p.stop,
        target: null,
        strategyId: p.strategyId,
        now,
      });
      next = r.book;
    }
  }
  return next;
}

export function flattenAll(book: PaperBook, quotes: Record<string, Quote>, now: number, risk: RiskSnapshot): PaperBook {
  let next = book;
  for (const p of [...book.positions]) {
    const q = quotes[p.symbol];
    if (!q) continue;
    const r = submitOrder(next, quotes, { ...risk, canTrade: true, breaches: [] }, {
      symbol: p.symbol,
      side: p.side === "BUY" ? "SELL" : "BUY",
      qty: p.qty,
      limitPrice: q.ltp,
      stop: p.stop,
      target: null,
      strategyId: "flatten",
      now,
    });
    next = r.book;
  }
  return next;
}

export function refreshDailyPnl(book: PaperBook, quotes: Record<string, Quote>): PaperBook {
  const nav = navOf(book, quotes);
  return { ...book, dailyPnl: nav - book.sessionStartNav };
}

export { snapshotRisk };
