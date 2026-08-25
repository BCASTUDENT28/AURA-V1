import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { EquityChart } from "@/components/aura/equity-chart";
import { Signed } from "@/components/aura/price";
import { SimBanner } from "@/components/aura/sim-banner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { experimentGrid, runBacktest } from "@/lib/aura/backtest";
import { formatInr, formatPct } from "@/lib/aura/format";
import { INSTRUMENTS } from "@/lib/aura/instruments";
import { STRATEGIES } from "@/lib/aura/strategies";
import { useAura } from "@/store/aura-store";

type Search = { symbol?: string; strategy?: string };

export const Route = createFileRoute("/lab")({
  validateSearch: (s: Record<string, unknown>): Search => ({
    symbol: typeof s.symbol === "string" ? s.symbol : undefined,
    strategy: typeof s.strategy === "string" ? s.strategy : undefined,
  }),
  component: LabPage,
});

function LabPage() {
  const search = Route.useSearch();
  const [symbol, setSymbol] = useState(search.symbol ?? "RELIANCE");
  const [strategyId, setStrategyId] = useState(search.strategy ?? "vwap_rsi");
  const result = useAura((s) => s.backtest);
  const busy = useAura((s) => s.backtestBusy);
  const setBacktest = useAura((s) => s.setBacktest);
  const setBusy = useAura((s) => s.setBacktestBusy);
  const [grid, setGrid] = useState<ReturnType<typeof experimentGrid>>([]);
  const def = STRATEGIES.find((s) => s.id === strategyId)!;

  const run = () => {
    setBusy(true);
    window.setTimeout(() => {
      const r = runBacktest({ strategyId, symbol, product: "INTRADAY" });
      setBacktest(r);
      setBusy(false);
      toast.message("Backtest complete — read costs and walk-forward before calling it an edge.");
    }, 40);
  };

  const runGrid = () => {
    setBusy(true);
    window.setTimeout(() => {
      setGrid(experimentGrid({ strategyId, symbol }));
      setBusy(false);
    }, 40);
  };

  const m = result?.metrics;
  const honest =
    m && (m.totalReturn <= 0 || m.maxDrawdown > 0.2 || (result.robust.warning ?? "").length > 0);

  return (
    <div className="mx-auto grid max-w-7xl gap-4">
      <div>
        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Versioned strategies</p>
        <h1 className="mt-1 text-2xl font-medium tracking-tight">Strategy lab</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Indian cost model is on: brokerage cap, STT, stamp, exchange, GST, 2 bps slippage. A pretty in-sample curve
          is not permission to trade. Walk-forward here is a prototype — audit leakage before you believe it.
        </p>
      </div>
      <SimBanner>
        Backtests run on simulated OHLC, not NSE history. Costs are unverified 2026 defaults. Do not treat the equity
        curve as evidence of edge.
      </SimBanner>
      <Card>
        <CardContent className="grid gap-3 p-4 md:grid-cols-4">
          <Field label="Strategy">
            <select className={sel} value={strategyId} onChange={(e) => setStrategyId(e.target.value)}>
              {STRATEGIES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} {s.version}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Symbol">
            <select className={sel} value={symbol} onChange={(e) => setSymbol(e.target.value)}>
              {INSTRUMENTS.map((i) => (
                <option key={i.symbol} value={i.symbol}>
                  {i.symbol}
                </option>
              ))}
            </select>
          </Field>
          <div className="flex items-end gap-2 md:col-span-2">
            <Button onClick={run} disabled={busy}>
              {busy ? "Running…" : "Run backtest"}
            </Button>
            <Button variant="outline" onClick={runGrid} disabled={busy}>
              Parameter grid
            </Button>
          </div>
          <p className="text-sm text-muted-foreground md:col-span-4">{def.summary}</p>
        </CardContent>
      </Card>

      {m && result && (
        <Tabs defaultValue="metrics">
          <TabsList>
            <TabsTrigger value="metrics">Metrics</TabsTrigger>
            <TabsTrigger value="walk">Walk-forward</TabsTrigger>
            <TabsTrigger value="trades">Trades</TabsTrigger>
            <TabsTrigger value="grid">Grid</TabsTrigger>
          </TabsList>
          <TabsContent value="metrics" className="mt-4 grid gap-4">
            {result.robust.warning && (
              <div className="rounded-xl bg-warn/10 px-4 py-3 text-sm text-warn">{result.robust.warning}</div>
            )}
            {honest && (
              <div className="rounded-xl bg-secondary px-4 py-3 text-sm text-muted-foreground">
                This run is not labelled profitable. {m.totalReturn <= 0 ? "Net return is non-positive after costs. " : ""}
                {m.maxDrawdown > 0.2 ? "Drawdown exceeds 20%. " : ""}
                Walk-forward and neighbor tests sit in the other tabs.
              </div>
            )}
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat k="Net P&L" v={formatInr(m.netPnl, true)} />
              <Stat k="Total return" v={<Signed value={m.totalReturn} pct />} />
              <Stat k="CAGR" v={<Signed value={m.cagr} pct />} />
              <Stat k="Sharpe" v={m.sharpe.toFixed(2)} />
              <Stat k="Sortino" v={m.sortino.toFixed(2)} />
              <Stat k="Max DD" v={formatPct(-m.maxDrawdown)} />
              <Stat k="Win rate" v={formatPct(m.winRate, 1)} />
              <Stat k="Profit factor" v={m.profitFactor.toFixed(2)} />
              <Stat k="Expectancy" v={formatInr(m.expectancy, true)} />
              <Stat k="Avg R" v={m.avgR.toFixed(2)} />
              <Stat k="Trades" v={String(m.trades)} />
              <Stat k="Costs" v={formatInr(m.costsTotal, true)} />
            </div>
            <Card>
              <CardHeader>
                <CardTitle>Equity (after costs)</CardTitle>
              </CardHeader>
              <CardContent>
                <EquityChart data={m.equity} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>By regime</CardTitle>
              </CardHeader>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead className="text-left text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2 font-medium">Regime</th>
                      <th className="px-4 py-2 font-medium">Trades</th>
                      <th className="px-4 py-2 font-medium">Win</th>
                      <th className="px-4 py-2 font-medium">P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {m.byRegime.map((r) => (
                      <tr key={r.regime} className="border-t border-border">
                        <td className="px-4 py-2">{r.regime}</td>
                        <td className="px-4 py-2 font-mono tabular-nums">{r.trades}</td>
                        <td className="px-4 py-2 font-mono tabular-nums">{formatPct(r.winRate, 0)}</td>
                        <td className="px-4 py-2">
                          <Signed value={r.pnl} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="walk" className="mt-4">
            <Card>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full text-sm">
                  <thead className="text-left text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2 font-medium">Window</th>
                      <th className="px-4 py-2 font-medium">Train</th>
                      <th className="px-4 py-2 font-medium">Test</th>
                      <th className="px-4 py-2 font-medium">Test ret</th>
                      <th className="px-4 py-2 font-medium">Win</th>
                      <th className="px-4 py-2 font-medium">Sharpe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.walkForward.map((w) => (
                      <tr key={w.window} className="border-t border-border">
                        <td className="px-4 py-2">{w.window}</td>
                        <td className="px-4 py-2 text-muted-foreground">{w.train}</td>
                        <td className="px-4 py-2 text-muted-foreground">{w.test}</td>
                        <td className="px-4 py-2">
                          <Signed value={w.testReturn} pct />
                        </td>
                        <td className="px-4 py-2 font-mono tabular-nums">{formatPct(w.testWinRate, 0)}</td>
                        <td className="px-4 py-2 font-mono tabular-nums">{w.testSharpe.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
            <p className="mt-3 text-sm text-muted-foreground">
              Neighbor-parameter stdev {(result.robust.neighborStd * 100).toFixed(1)}%. High dispersion means the fit is
              fragile.
            </p>
          </TabsContent>
          <TabsContent value="trades" className="mt-4">
            <Card>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full min-w-[640px] text-sm">
                  <thead className="text-left text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2 font-medium">Side</th>
                      <th className="px-4 py-2 font-medium">Entry</th>
                      <th className="px-4 py-2 font-medium">Exit</th>
                      <th className="px-4 py-2 font-medium">P&L</th>
                      <th className="px-4 py-2 font-medium">R</th>
                      <th className="px-4 py-2 font-medium">Costs</th>
                      <th className="px-4 py-2 font-medium">Why</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.slice(-40).reverse().map((t, i) => (
                      <tr key={i} className="border-t border-border">
                        <td className="px-4 py-2">{t.side}</td>
                        <td className="px-4 py-2 font-mono tabular-nums">{t.entry.toFixed(2)}</td>
                        <td className="px-4 py-2 font-mono tabular-nums">{t.exit.toFixed(2)}</td>
                        <td className="px-4 py-2">
                          <Signed value={t.pnl} />
                        </td>
                        <td className="px-4 py-2 font-mono tabular-nums">{t.rMultiple.toFixed(2)}</td>
                        <td className="px-4 py-2 font-mono tabular-nums">{t.costs.toFixed(0)}</td>
                        <td className="px-4 py-2 text-muted-foreground">{t.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="grid" className="mt-4">
            <p className="mb-3 text-sm text-muted-foreground">
              Ranked by Sharpe, not raw profit. The top row is not "the best strategy" — check drawdown and neighbor
              stability.
            </p>
            <Button variant="outline" size="sm" onClick={runGrid} className="mb-3">
              {grid.length ? "Re-run grid" : "Run 27 combinations"}
            </Button>
            <GridTable rows={grid} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}

const sel =
  "h-10 w-full rounded-md bg-secondary px-3 text-sm shadow-[var(--shadow-border)]";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5">
      <span className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function Stat({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="rounded-xl bg-card p-3 shadow-[var(--shadow-border)]">
      <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{k}</div>
      <div className="mt-1 font-mono text-lg tabular-nums">{v}</div>
    </div>
  );
}

function GridTable({ rows }: { rows: ReturnType<typeof experimentGrid> }) {
  const shown = useMemo(() => rows.slice(0, 12), [rows]);
  if (!shown.length) return <p className="text-sm text-muted-foreground">Run the grid to rank parameter sets.</p>;
  return (
    <Card>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="text-left text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">Params</th>
              <th className="px-4 py-2 font-medium">Return</th>
              <th className="px-4 py-2 font-medium">Sharpe</th>
              <th className="px-4 py-2 font-medium">DD</th>
              <th className="px-4 py-2 font-medium">Win</th>
              <th className="px-4 py-2 font-medium">N</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.label} className="border-t border-border">
                <td className="px-4 py-2 text-xs">{r.label}</td>
                <td className="px-4 py-2">
                  <Signed value={r.totalReturn} pct />
                </td>
                <td className="px-4 py-2 font-mono tabular-nums">{r.sharpe.toFixed(2)}</td>
                <td className="px-4 py-2 font-mono tabular-nums">{formatPct(-r.maxDrawdown)}</td>
                <td className="px-4 py-2 font-mono tabular-nums">{formatPct(r.winRate, 0)}</td>
                <td className="px-4 py-2 font-mono tabular-nums">{r.trades}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
