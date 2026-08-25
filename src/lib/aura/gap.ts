export type GapVerdict = "KEEP" | "MODIFY" | "REWRITE" | "REMOVE" | "BUILD NEW" | "PLATFORM";
export type GapPhase = "V0.1" | "P2" | "later";

export interface GapFile {
  path: string;
  verdict: GapVerdict;
  phase: GapPhase;
  why: string;
}

export const GAP_SCORES = {
  ui: 8,
  quant: 6,
  research: 4,
  ml: 2,
  production: 1,
  safety: 5,
} as const;

export const GAP_PRINCIPLES = [
  "Do not delete this prototype. Treat it as AURA V0.1, not the finished engine.",
  "Do not redesign the desk UI. Charts, tickets, lab, paper, risk, memory, research stay.",
  "Do not connect Angel One or Groww. Live execution stays sealed.",
  "Do not treat simulated prices, fake news, or heuristic probabilities as evidence of edge.",
  "Browser is no longer the brain. Postgres is the ledger. The tape is still a simulator.",
  "This sandbox ships TanStack Start server functions + Postgres, not FastAPI. Same split: UI → server → DB.",
] as const;

export const GAP_PHASES: { id: string; title: string; status: "done" | "now" | "next"; body: string }[] = [
  {
    id: "p1",
    title: "Phase 1 — Preserve the desk",
    status: "done",
    body: "Keep Overview, Signals, Strategy lab, Paper, Portfolio, Risk, Memory, News, Research. Honest PAPER / SIMULATED labels.",
  },
  {
    id: "p2",
    title: "Phase 2 — Ledger leaves the browser",
    status: "now",
    body: "Paper sessions, orders, fills, memory and versioned cost/lineage live in Postgres. Reset archives; it does not wipe history. No live trading.",
  },
  {
    id: "p3",
    title: "Phase 3 — Data provider",
    status: "next",
    body: "Keep the simulator behind a DataProvider. Add HistoricalDataProvider before any live feed. V1 can be historical first.",
  },
  {
    id: "p4",
    title: "Phase 4 — Paper book as tables",
    status: "now",
    body: "paper_orders / paper_fills / paper_book_state are the source of truth. localStorage is a cache only.",
  },
  {
    id: "p5",
    title: "Phase 5 — Lineage records",
    status: "now",
    body: "strategy / model / feature / dataset / cost versions are database rows, not string constants glued onto a decision.",
  },
  {
    id: "p6",
    title: "Phase 6 — Actual ML",
    status: "next",
    body: "RegimeModel and DirectionModel first. Anomaly and volatility later. Heuristic probabilities stay labelled as rules.",
  },
  {
    id: "p7",
    title: "Phase 7 — Research-grade backtests",
    status: "next",
    body: "Audit leakage, look-ahead, intrabar fills, costs, walk-forward, multiple testing. Do not trust the pretty equity curve yet.",
  },
  {
    id: "p8",
    title: "Phase 8 — Similarity + memory",
    status: "next",
    body: "Research-grade neighbors, min sample, revalidate_after, strategy/model/feature/dataset ids on every learning.",
  },
  {
    id: "p9",
    title: "Phase 9 — Broker adapter",
    status: "next",
    body: "BrokerExecutionInterface → AngelOneAdapter. Groww is V2. Interface exists now and always refuses.",
  },
  {
    id: "p10",
    title: "Phase 10 — Controlled live",
    status: "next",
    body: "Only after extensive paper validation: human-approved, size-capped, kill-switch live. Automatic live is last.",
  },
];

export const GAP_FILES: GapFile[] = [
  // Desk UI — keep
  { path: "src/components/aura/app-shell.tsx", verdict: "MODIFY", phase: "P2", why: "Keep chrome. Add Gap nav, SIMULATED tape badge, ledger status. Do not restyle." },
  { path: "src/components/aura/candle-chart.tsx", verdict: "KEEP", phase: "V0.1", why: "Desk chart. Reuse." },
  { path: "src/components/aura/equity-chart.tsx", verdict: "KEEP", phase: "V0.1", why: "Backtest equity. Reuse." },
  { path: "src/components/aura/order-ticket.tsx", verdict: "KEEP", phase: "V0.1", why: "Limit + stop required. Matches risk policy." },
  { path: "src/components/aura/price.tsx", verdict: "KEEP", phase: "V0.1", why: "Signed P&L / action chips." },
  { path: "src/components/aura/signal-detail.tsx", verdict: "KEEP", phase: "V0.1", why: "Evidence + lineage drawer. Keep copy honest." },
  { path: "src/components/aura/sim-banner.tsx", verdict: "BUILD NEW", phase: "P2", why: "Shared honest-source banner so simulated tape/news cannot be mistaken for live." },
  { path: "src/components/ui/*", verdict: "KEEP", phase: "V0.1", why: "shadcn primitives. Do not restyle." },
  { path: "src/routes/__root.tsx", verdict: "KEEP", phase: "V0.1", why: "Document shell. AuthProvider + PreviewHostBridge stay." },
  { path: "src/routes/index.tsx", verdict: "MODIFY", phase: "P2", why: "Keep overview. Label tape as simulated. Point at Gap." },
  { path: "src/routes/signals.tsx", verdict: "KEEP", phase: "V0.1", why: "Signal board. Heuristic probs already shown as confidence, not ML." },
  { path: "src/routes/lab.tsx", verdict: "MODIFY", phase: "later", why: "Keep lab. Later: leakage warnings on every backtest result." },
  { path: "src/routes/paper.tsx", verdict: "MODIFY", phase: "P2", why: "Keep ticket/positions. Show Postgres session id and archive-on-reset." },
  { path: "src/routes/portfolio.tsx", verdict: "KEEP", phase: "V0.1", why: "Paper NAV view. Reuse." },
  { path: "src/routes/risk.tsx", verdict: "MODIFY", phase: "P2", why: "Keep gates UI. Static IP is a paper exemption, not a live verification. Live path sealed." },
  { path: "src/routes/memory.tsx", verdict: "MODIFY", phase: "P2", why: "Keep empty-until-traded copy. Learnings now persist with lineage ids." },
  { path: "src/routes/news.tsx", verdict: "MODIFY", phase: "P2", why: "Keep layout. Banner: SAMPLE headlines, not a news feed." },
  { path: "src/routes/research.tsx", verdict: "KEEP", phase: "V0.1", why: "User-initiated explainer over supplied evidence. Philosophy is correct." },
  { path: "src/routes/more.tsx", verdict: "MODIFY", phase: "P2", why: "Add Gap report + architecture links for mobile." },
  { path: "src/routes/gap.tsx", verdict: "BUILD NEW", phase: "P2", why: "Frozen KEEP/MODIFY/REWRITE/REMOVE/BUILD NEW for every source file." },
  { path: "src/styles.css", verdict: "KEEP", phase: "V0.1", why: "IBM Plex + desk tokens. Do not introduce a second palette." },
  { path: "src/store/aura-store.ts", verdict: "MODIFY", phase: "P2", why: "Hydrate/persist paper book via server. localStorage is cache. Do not tick-write the DB." },

  // Quant engine
  { path: "src/lib/aura/types.ts", verdict: "MODIFY", phase: "P2", why: "Add costVersion, dataSource, livePathSealed, session ids. Keep domain types." },
  { path: "src/lib/aura/rng.ts", verdict: "KEEP", phase: "V0.1", why: "Deterministic PRNG for the simulator. Fine." },
  { path: "src/lib/aura/format.ts", verdict: "KEEP", phase: "V0.1", why: "INR / IST / regime labels." },
  { path: "src/lib/aura/instruments.ts", verdict: "KEEP", phase: "V0.1", why: "NIFTY 50 subset + BANKNIFTY. Universe note already says simulated." },
  { path: "src/lib/aura/indicators.ts", verdict: "KEEP", phase: "V0.1", why: "Rules V1 feature pack. Later version in DB as feat-v1." },
  { path: "src/lib/aura/strategies.ts", verdict: "KEEP", phase: "V0.1", why: "MA cross, VWAP+RSI, ORB. Aligns with V1 scope. Do not rewrite." },
  { path: "src/lib/aura/regime.ts", verdict: "KEEP", phase: "V0.1", why: "ADX/RV/DI rules baseline. Keep until Regime ML exists. Label as rules." },
  { path: "src/lib/aura/market.ts", verdict: "MODIFY", phase: "later", why: "Synthetic OHLC. Keep as SimulatorProvider. Do not pretend it is NSE. Replace later via DataProvider." },
  { path: "src/lib/aura/provider.ts", verdict: "BUILD NEW", phase: "P2", why: "DataProvider interface. Only SIMULATOR is wired. Historical/live are stubs that refuse." },
  { path: "src/lib/aura/decision.ts", verdict: "MODIFY", phase: "later", why: "Heuristic blend of strategy + regime + similarity. Keep as rules engine. Do not call it ML. Lineage from DB ids." },
  { path: "src/lib/aura/similarity.ts", verdict: "MODIFY", phase: "later", why: "Directionally right feature vector. Not research-grade (distance, sampling, leakage). Keep as prototype." },
  { path: "src/lib/aura/cost.ts", verdict: "MODIFY", phase: "P2", why: "Keep formula. Rates become versioned aura_cost_config rows marked unverified." },
  { path: "src/lib/aura/paper.ts", verdict: "MODIFY", phase: "P2", why: "Keep fill/stop/flatten math. Persistence moves to server. Engine stays in-process for the tick." },
  { path: "src/lib/aura/risk.ts", verdict: "MODIFY", phase: "later", why: "Policy demo, not production compliance. Keep PAPER gates. Rewrite before any live path. staticIpOk must not be caller-true on live." },
  { path: "src/lib/aura/memory.ts", verdict: "MODIFY", phase: "P2", why: "Keep n≥5 flag. Persist with strategy/model/feature/dataset ids. min_sample_required + revalidate_after later." },
  { path: "src/lib/aura/backtest.ts", verdict: "MODIFY", phase: "later", why: "Substantial prototype (Sharpe, WF, neighbors). Audit leakage/intrabar/costs before trusting. Keep as research toy." },
  { path: "src/lib/aura/news.ts", verdict: "MODIFY", phase: "later", why: "Hardcoded headlines + deterministic timestamps. Keep as SAMPLE. Real pipeline is later." },
  { path: "src/lib/aura/ai.ts", verdict: "KEEP", phase: "V0.1", why: "User-initiated, evidence-only, no orders. Correct philosophy. Not a trading authority." },
  { path: "src/lib/aura/broker.ts", verdict: "BUILD NEW", phase: "P2", why: "BrokerExecutionInterface. Always refuses. Angel One adapter is Phase 9." },
  { path: "src/lib/aura/server.ts", verdict: "BUILD NEW", phase: "P2", why: "createServerFn ledger: sessions, orders, fills, memory, lineage, cost config." },
  { path: "src/lib/aura/gap.ts", verdict: "BUILD NEW", phase: "P2", why: "This freeze. Change only when a file's verdict changes." },

  // Platform — do not touch
  { path: "src/lib/auth/*", verdict: "PLATFORM", phase: "later", why: "Auth stays OFF until a real multi-user ask. Do not import authMiddleware on an auth-off desk." },
  { path: "src/lib/db.ts", verdict: "PLATFORM", phase: "V0.1", why: "Neon + PGLite helper. Use from server functions only." },
  { path: "src/lib/app-data/*", verdict: "PLATFORM", phase: "V0.1", why: "Connector SDK. Not used. Never call from the client." },
  { path: "src/lib/preview-host-bridge.ts", verdict: "PLATFORM", phase: "V0.1", why: "Preview chrome. Do not strip." },
  { path: "src/components/preview-host-bridge.tsx", verdict: "PLATFORM", phase: "V0.1", why: "Must stay mounted." },
  { path: "src/router.tsx", verdict: "PLATFORM", phase: "V0.1", why: "Named getRouter() + AppErrorComponent." },
  { path: "vite.config.ts", verdict: "PLATFORM", phase: "V0.1", why: "Do not recreate. Keep grokPwaPlugin and port contract." },
  { path: "public/__grok/*", verdict: "PLATFORM", phase: "V0.1", why: "Platform chrome. Never delete." },
  { path: "migrations/auth/0001_auth.sql", verdict: "PLATFORM", phase: "later", why: "Do not copy up until sign-in is explicitly turned on." },
  { path: "migrations/0002_aura_core.sql", verdict: "BUILD NEW", phase: "P2", why: "Paper ledger, lineage, cost config, memory." },

  // Explicitly not now
  { path: "Angel One adapter", verdict: "BUILD NEW", phase: "later", why: "Phase 9. Connecting it now would be the mistake." },
  { path: "Groww adapter", verdict: "BUILD NEW", phase: "later", why: "V2." },
  { path: "Regime / Direction ML", verdict: "BUILD NEW", phase: "later", why: "Phase 6. Current MODEL_VERSION is regime-rules-v1 heuristics." },
  { path: "RAG / knowledge", verdict: "BUILD NEW", phase: "later", why: "Not in V0.1. Research desk uses supplied evidence only." },
  { path: "Live market data", verdict: "BUILD NEW", phase: "later", why: "Phase 3. Simulator stays until a HistoricalDataProvider exists." },
  { path: "FastAPI extract", verdict: "BUILD NEW", phase: "later", why: "Target architecture named FastAPI. This desk runs TanStack Start. Same split; extract later if the stack leaves this sandbox." },
];

export const GAP_KEEP = GAP_FILES.filter((f) => f.verdict === "KEEP");
export const GAP_MODIFY = GAP_FILES.filter((f) => f.verdict === "MODIFY");
export const GAP_REWRITE = GAP_FILES.filter((f) => f.verdict === "REWRITE");
export const GAP_REMOVE = GAP_FILES.filter((f) => f.verdict === "REMOVE");
export const GAP_BUILD = GAP_FILES.filter((f) => f.verdict === "BUILD NEW");
export const GAP_PLATFORM = GAP_FILES.filter((f) => f.verdict === "PLATFORM");
