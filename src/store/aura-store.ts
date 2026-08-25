/**
 * src/store/aura-store.ts — Phase 1 migration
 *
 * WHAT CHANGED:
 *   - decideUniverse()  → fetch("/api/universe/decisions")  [Python backend]
 *   - snapshotRisk()    → fetch("/api/risk/snapshot")       [Python backend]
 *   - estimateCosts()   → POST "/api/paper/order"           [Python backend]
 *
 * WHAT STAYS:
 *   - All paper-book local state management (matchWorking, checkStops, etc.)
 *   - Zustand store shape — identical to before this migration
 *   - All UI behaviour — screens show identical values, same seed
 *
 * ⚠️  DEAD CODE note:
 *   src/lib/aura/decision.ts, risk.ts, cost.ts are kept in the repo,
 *   unused, clearly marked dead code. Only delete them after all 3 seeds
 *   pass the Python parity tests.
 */

import { create } from "zustand";
// ⚠️ DEAD CODE — the following imports are NOT used by application code.
// They exist only so the parity test script (scripts/dump-ts-canonical.mjs)
// can import them. Do not call decideUniverse/snapshotRisk/estimateCosts
// from application code.
// import { decideUniverse } from "@/lib/aura/decision";  // DEAD CODE
// import { snapshotRisk } from "@/lib/aura/risk";        // DEAD CODE
// import { estimateCosts } from "@/lib/aura/cost";       // DEAD CODE

import { INSTRUMENTS } from "@/lib/aura/instruments";
import { getUniverse, PAPER_OPEN, seedQuotes, stepQuotes } from "@/lib/aura/market";
import { recordClose } from "@/lib/aura/memory";
import { getNews } from "@/lib/aura/news";
import {
  checkStops,
  emptyBook,
  flattenAll,
  matchWorking,
  navOf,
  refreshDailyPnl,
  submitOrder,
  type PaperBook,
} from "@/lib/aura/paper";
import {
  archiveAndReset,
  loadDesk,
  persistDesk,
  recordLearning,
  recordPaperOrder,
} from "@/lib/aura/server";
import type {
  BacktestResult,
  Decision,
  Learning,
  NewsItem,
  Quote,
  RiskSnapshot,
} from "@/lib/aura/types";
import { STARTING_CASH } from "@/lib/aura/types";

// ---------------------------------------------------------------------------
// Backend API base URL (set VITE_API_BASE in .env.local, default = localhost)
// ---------------------------------------------------------------------------
const API_BASE =
  (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_API_BASE) ||
  "http://localhost:8000";

const LS_KEY = "aura-paper-v1";

function loadBook(): PaperBook {
  if (typeof window === "undefined") return emptyBook();
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return emptyBook();
    return { ...emptyBook(), ...JSON.parse(raw) };
  } catch {
    return emptyBook();
  }
}

function saveBook(book: PaperBook) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(book));
  } catch {
    /* ignore */
  }
}

// ---------------------------------------------------------------------------
// Backend fetch helpers (replace the old local computation)
// ---------------------------------------------------------------------------

/** Fetch decisions from the Python backend. */
async function fetchDecisions(): Promise<Decision[]> {
  const res = await fetch(`${API_BASE}/api/universe/decisions`);
  if (!res.ok) throw new Error(`decisions fetch failed: ${res.status}`);
  return res.json();
}

/** Fetch risk snapshot from the Python backend. */
async function fetchRiskSnapshot(args: {
  killSwitch: boolean;
  now: number;
  lastTick: number;
  dailyPnl: number;
  opsWindowLen: number;
}): Promise<RiskSnapshot> {
  const params = new URLSearchParams({
    kill_switch: String(args.killSwitch),
    now: String(args.now),
    last_tick: String(args.lastTick),
    daily_pnl: String(args.dailyPnl),
    ops_window_len: String(args.opsWindowLen),
  });
  const res = await fetch(`${API_BASE}/api/risk/snapshot?${params}`);
  if (!res.ok) throw new Error(`risk snapshot fetch failed: ${res.status}`);
  return res.json();
}

/** Send a paper order to the Python backend (costs + risk validation). */
async function postPaperOrder(body: {
  symbol: string;
  side: "BUY" | "SELL";
  qty: number;
  limit_price: number;
  stop: number | null;
  target: number | null;
  strategy_id: string | null;
  kill_switch: boolean;
  now: number;
  last_tick: number;
  daily_pnl: number;
  ops_window: number[];
}): Promise<{ ok: boolean; message: string; cost?: unknown; risk?: RiskSnapshot }> {
  const res = await fetch(`${API_BASE}/api/paper/order`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`paper/order failed: ${res.status} ${err}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Fallback: construct a canTrade=false stub when the backend is unreachable
// ---------------------------------------------------------------------------
function offlineRiskSnap(
  killSwitch: boolean,
  now: number,
  lastTick: number,
  dailyPnl: number,
  opsWindow: number[],
): RiskSnapshot {
  return {
    killSwitch,
    dailyPnl,
    dailyPnlPct: dailyPnl / STARTING_CASH,
    exposurePct: 0,
    openPositions: 0,
    dataAgeMs: now - lastTick,
    opsWindow,
    staticIpOk: false,
    env: "PAPER",
    livePathSealed: true,
    dataSource: "SIMULATOR",
    breaches: ["Backend unreachable — trading disabled."],
    canTrade: false,
  };
}

// ---------------------------------------------------------------------------
// Initial state — fetched lazily after store mounts
// ---------------------------------------------------------------------------
const universe = getUniverse();
const initialQuotes = seedQuotes(PAPER_OPEN);
const initialNews = getNews(PAPER_OPEN);
const initialBook = emptyBook();
const initialRisk: RiskSnapshot = offlineRiskSnap(false, PAPER_OPEN, PAPER_OPEN, 0, []);

export type PersistSource = "local" | "postgres" | "syncing";

export interface AuraState {
  now: number;
  tickN: number;
  quotes: Record<string, Quote>;
  signals: Decision[];
  book: PaperBook;
  riskSnap: RiskSnapshot;
  learnings: Learning[];
  news: NewsItem[];
  killSwitch: boolean;
  opsWindow: number[];
  lastTick: number;
  selectedSymbol: string;
  backtest: BacktestResult | null;
  backtestBusy: boolean;
  hydrated: boolean;
  sessionId: string | null;
  persistSource: PersistSource;
  costNote: string | null;
  // Async setters (return void, update store asynchronously)
  hydrate: () => void;
  tick: () => void;
  setSymbol: (s: string) => void;
  setKill: (v: boolean) => void;
  place: (input: {
    symbol: string;
    side: "BUY" | "SELL";
    qty: number;
    limitPrice: number;
    stop: number | null;
    target: number | null;
    strategyId: string | null;
  }) => Promise<{ ok: boolean; message: string }>;
  flatten: () => void;
  resetPaper: () => void;
  setBacktest: (r: BacktestResult | null) => void;
  setBacktestBusy: (v: boolean) => void;
  risk: () => RiskSnapshot;
  nav: () => number;
  // Backend signals fetch (called on init + every 8 ticks)
  refreshSignals: () => Promise<void>;
  refreshRisk: () => Promise<void>;
}

function flushDesk(s: Pick<AuraState, "sessionId" | "book" | "learnings" | "killSwitch">) {
  if (!s.sessionId) return;
  persistDesk({
    data: {
      sessionId: s.sessionId,
      book: s.book,
      learnings: s.learnings,
      killSwitch: s.killSwitch,
    },
  }).catch(() => {
    /* ledger write is best-effort in preview; local cache remains */
  });
}

export const useAura = create<AuraState>((set, get) => ({
  now: PAPER_OPEN,
  tickN: 0,
  quotes: initialQuotes,
  signals: [],            // populated by refreshSignals() on hydrate
  book: initialBook,
  riskSnap: initialRisk,  // populated by refreshRisk() on hydrate
  learnings: [],
  news: initialNews,
  killSwitch: false,
  opsWindow: [],
  lastTick: PAPER_OPEN,
  selectedSymbol: "NIFTY",
  backtest: null,
  backtestBusy: false,
  hydrated: false,
  sessionId: null,
  persistSource: "local",
  costNote: null,

  // -------------------------------------------------------------------------
  // refreshSignals — replaces decideUniverse() local call
  // -------------------------------------------------------------------------
  refreshSignals: async () => {
    try {
      const signals = await fetchDecisions();
      set({ signals });
    } catch {
      // Keep stale signals — don't clear on transient errors
    }
  },

  // -------------------------------------------------------------------------
  // refreshRisk — replaces snapshotRisk() local call
  // -------------------------------------------------------------------------
  refreshRisk: async () => {
    const s = get();
    try {
      const snap = await fetchRiskSnapshot({
        killSwitch: s.killSwitch,
        now: s.now,
        lastTick: s.lastTick,
        dailyPnl: s.book.dailyPnl,
        opsWindowLen: s.opsWindow.length,
      });
      set({ riskSnap: snap });
    } catch {
      set({
        riskSnap: offlineRiskSnap(
          s.killSwitch, s.now, s.lastTick, s.book.dailyPnl, s.opsWindow,
        ),
      });
    }
  },

  // -------------------------------------------------------------------------
  // hydrate
  // -------------------------------------------------------------------------
  hydrate: () => {
    if (get().hydrated) return;
    const book = loadBook();
    set({ book, hydrated: true, persistSource: "syncing" });

    // Fetch initial signals and risk from backend
    void get().refreshSignals();
    void get().refreshRisk();

    void loadDesk()
      .then((desk) => {
        saveBook(desk.book);
        set({
          book: desk.book,
          learnings: desk.learnings,
          killSwitch: desk.killSwitch,
          sessionId: desk.sessionId,
          persistSource: "postgres",
          costNote: desk.cost?.sourceNote ?? null,
        });
        // Re-fetch risk with updated book state
        void get().refreshRisk();
      })
      .catch(() => {
        set({ persistSource: "local" });
      });
  },

  // -------------------------------------------------------------------------
  // tick
  // -------------------------------------------------------------------------
  tick: () => {
    const s = get();
    const now = s.now + 1000;
    const quotes = stepQuotes(s.quotes, 1, now, s.tickN + 1);
    let book = matchWorking(s.book, quotes, now);
    const before = new Set(book.positions.map((p) => p.symbol));
    // We need a local risk snap for stop-check — use the last known riskSnap
    const riskForStops = { ...s.riskSnap, canTrade: true, breaches: [] };
    book = checkStops(book, quotes, now, riskForStops);
    book = refreshDailyPnl(book, quotes);

    const learnings = [...s.learnings];
    const newLearnings: Learning[] = [];
    for (const p of s.book.positions) {
      if (before.has(p.symbol) && !book.positions.some((x) => x.symbol === p.symbol)) {
        const q = quotes[p.symbol];
        const item = recordClose({
          position: p,
          exit: q?.ltp ?? p.avgPrice,
          now,
          regime: s.signals.find((d) => d.symbol === p.symbol)?.regime.label ?? "RANGE",
        });
        learnings.unshift(item);
        newLearnings.push(item);
      }
    }
    saveBook(book);
    const tickN = s.tickN + 1;
    set({ now, quotes, book, lastTick: now, tickN, learnings });

    // Refresh risk snapshot from backend every tick
    void get().refreshRisk();

    // Refresh signals from backend every 8 ticks
    if (tickN % 8 === 0) {
      void get().refreshSignals();
    }

    if (newLearnings.length > 0 && s.sessionId) {
      flushDesk({ sessionId: s.sessionId, book, learnings, killSwitch: s.killSwitch });
      for (const item of newLearnings) {
        recordLearning({ data: { sessionId: s.sessionId, item } }).catch(() => undefined);
      }
    }
  },

  setSymbol: (selectedSymbol) => set({ selectedSymbol }),

  setKill: (killSwitch) => {
    set({ killSwitch });
    void get().refreshRisk();
    const s = get();
    flushDesk(s);
  },

  // -------------------------------------------------------------------------
  // place — uses backend for risk + cost validation
  // -------------------------------------------------------------------------
  place: async (input) => {
    const s = get();
    const opsWindow = [s.now, ...s.opsWindow].slice(0, 40);

    // Validate + get costs from backend
    let backendResult: { ok: boolean; message: string; cost?: unknown; risk?: RiskSnapshot };
    try {
      backendResult = await postPaperOrder({
        symbol: input.symbol,
        side: input.side,
        qty: input.qty,
        limit_price: input.limitPrice,
        stop: input.stop,
        target: input.target,
        strategy_id: input.strategyId,
        kill_switch: s.killSwitch,
        now: s.now,
        last_tick: s.lastTick,
        daily_pnl: s.book.dailyPnl,
        ops_window: opsWindow,
      });
    } catch {
      return { ok: false, message: "Backend unreachable — order rejected." };
    }

    if (!backendResult.ok) {
      if (backendResult.risk) set({ riskSnap: backendResult.risk });
      return { ok: false, message: backendResult.message };
    }

    // Apply order locally (paper matching engine stays in frontend)
    const { book, order } = submitOrder(s.book, s.quotes, s.riskSnap, {
      ...input,
      now: s.now,
    });
    saveBook(book);
    set({ book, opsWindow });

    // Update risk from backend
    if (backendResult.risk) set({ riskSnap: backendResult.risk });
    else void get().refreshRisk();

    if (s.sessionId) {
      const fill = book.fills.find((f) => f.orderId === order.id) ?? null;
      recordPaperOrder({
        data: {
          sessionId: s.sessionId,
          order,
          fill,
          lineage: {
            strategyVersion: order.strategyId ?? "discretionary",
            modelVersion: "regime-rules-v1",
            datasetVersion: "sim-in-eq-20240821",
            costVersion: "in-cash-2026-unverified-v1",
          },
        },
      }).catch(() => undefined);
      flushDesk({ sessionId: s.sessionId, book, learnings: s.learnings, killSwitch: s.killSwitch });
    }

    if (order.status === "REJECTED") return { ok: false, message: order.rejectReason ?? "Rejected" };
    if (order.status === "FILLED")
      return { ok: true, message: `Filled ${order.qty} ${order.symbol} @ ${order.fillPrice}` };
    return {
      ok: true,
      message: `Working limit ${order.side} ${order.qty} ${order.symbol} @ ${order.limitPrice}`,
    };
  },

  flatten: () => {
    const s = get();
    const book = flattenAll(s.book, s.quotes, s.now, {
      ...s.riskSnap,
      canTrade: true,
      breaches: [],
    });
    saveBook(book);
    set({ book });
    void get().refreshRisk();
    flushDesk({ sessionId: s.sessionId, book, learnings: s.learnings, killSwitch: s.killSwitch });
  },

  resetPaper: () => {
    const s = get();
    const apply = (book: PaperBook, sessionId: string | null, persistSource: PersistSource) => {
      saveBook(book);
      set({ book, learnings: [], sessionId, persistSource });
      void get().refreshRisk();
    };
    if (s.sessionId) {
      void archiveAndReset({ data: { sessionId: s.sessionId } })
        .then((r) => apply(r.book, r.sessionId, "postgres"))
        .catch(() => apply(emptyBook(), s.sessionId, "local"));
      return;
    }
    apply(emptyBook(), null, "local");
  },

  setBacktest: (backtest) => set({ backtest }),
  setBacktestBusy: (backtestBusy) => set({ backtestBusy }),
  risk: () => get().riskSnap,
  nav: () => navOf(get().book, get().quotes),
}));

export { universe, INSTRUMENTS, STARTING_CASH };
