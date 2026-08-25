import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { CandleChart, Sparkline } from "@/components/aura/candle-chart";
import { ActionChip, Price, Signed } from "@/components/aura/price";
import { SignalDetail } from "@/components/aura/signal-detail";
import { SimBanner } from "@/components/aura/sim-banner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { INSTRUMENTS, SECTORS } from "@/lib/aura/instruments";
import { barsOf, getUniverse, sectorReturn } from "@/lib/aura/market";
import { classifyRegime } from "@/lib/aura/regime";
import { REGIME_LABEL, formatInrCompact, formatVolume } from "@/lib/aura/format";
import type { Decision } from "@/lib/aura/types";
import { useAura } from "@/store/aura-store";

export const Route = createFileRoute("/")({ component: Overview });

function Overview() {
  const quotes = useAura((s) => s.quotes);
  const signals = useAura((s) => s.signals);
  const book = useAura((s) => s.book);
  const nav = useAura((s) => s.nav());
  const risk = useAura((s) => s.riskSnap);
  const selected = useAura((s) => s.selectedSymbol);
  const setSymbol = useAura((s) => s.setSymbol);
  const [open, setOpen] = useState<Decision | null>(null);
  const niftyBars = barsOf("NIFTY", "1D");
  const regime = classifyRegime(niftyBars);
  const quality = getUniverse().quality;
  const actionable = signals.filter((d) => d.action === "BUY" || d.action === "SELL").slice(0, 8);
  const sectors = useMemo(
    () =>
      SECTORS.filter((s) => s !== "Index")
        .map((s) => ({ s, r: sectorReturn(quotes, s) }))
        .sort((a, b) => b.r - a.r),
    [quotes],
  );

  return (
    <div className="mx-auto grid min-w-0 max-w-7xl gap-4">
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Intelligence OS</p>
          <h1 className="mt-1 text-2xl font-medium tracking-tight md:text-3xl">Indian cash desk</h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            Probabilities, evidence, and a risk veto. Not a forecast. Live trading is disabled. Tape is simulated.
          </p>
        </div>
        <div className="text-[11px] text-muted-foreground sm:text-right">
          Data {quality.status} · {quality.timezone} · CA-adjusted · {quality.datasetVersion}
        </div>
      </div>
      <SimBanner />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <IndexCard symbol="NIFTY" />
        <IndexCard symbol="BANKNIFTY" />
        <Card>
          <CardHeader>
            <CardTitle>Market regime</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-lg font-medium">{REGIME_LABEL[regime.label]}</div>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{regime.notes}</p>
            <div className="mt-3 flex gap-3 font-mono text-xs tabular-nums text-muted-foreground">
              <span>ADX {regime.adx.toFixed(1)}</span>
              <span>RV {(regime.realizedVol * 100).toFixed(1)}%</span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Paper book</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="font-mono text-2xl tabular-nums">{formatInrCompact(nav)}</div>
            <div className="mt-1 text-sm">
              Day P&L <Signed value={book.dailyPnl / 1_000_000} pct />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
              <span>Positions {book.positions.length}</span>
              <span>Exposure {(risk.exposurePct * 100).toFixed(0)}%</span>
              <span className={risk.canTrade ? "text-up" : "text-down"}>
                {risk.canTrade ? "Risk clear" : "Risk blocked"}
              </span>
              <span>{risk.killSwitch ? "Kill on" : "Kill off"}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle>{selected} · daily</CardTitle>
            <select
              className="h-8 rounded-md bg-secondary px-2 text-xs shadow-[var(--shadow-border)]"
              value={selected}
              onChange={(e) => setSymbol(e.target.value)}
            >
              {INSTRUMENTS.map((i) => (
                <option key={i.symbol} value={i.symbol}>
                  {i.symbol}
                </option>
              ))}
            </select>
          </CardHeader>
          <CardContent className="h-56">
            <CandleChart bars={barsOf(selected, "1D")} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Sector tape</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-1.5">
            {sectors.map(({ s, r }) => (
              <div key={s} className="flex items-center gap-3">
                <div className="w-20 text-xs text-muted-foreground">{s}</div>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full ${r >= 0 ? "bg-up" : "bg-down"}`}
                    style={{ width: `${Math.min(100, Math.abs(r) * 1400)}%` }}
                  />
                </div>
                <div className="w-14 text-right font-mono text-xs tabular-nums">
                  <Signed value={r} pct />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Active signals</CardTitle>
          <Link to="/signals" className="text-xs text-muted-foreground hover:text-foreground">
            Full board
          </Link>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="text-left text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Symbol</th>
                <th className="px-4 py-2 font-medium">Action</th>
                <th className="px-4 py-2 font-medium">Conf</th>
                <th className="px-4 py-2 font-medium">Regime</th>
                <th className="px-4 py-2 font-medium">R:R</th>
                <th className="px-4 py-2 font-medium">Why</th>
              </tr>
            </thead>
            <tbody>
              {actionable.map((d) => (
                <tr
                  key={d.id}
                  className="cursor-pointer border-t border-border hover:bg-accent/40"
                  onClick={() => setOpen(d)}
                >
                  <td className="px-4 py-2.5 font-medium">{d.symbol}</td>
                  <td className="px-4 py-2.5">
                    <ActionChip action={d.action} />
                  </td>
                  <td className="px-4 py-2.5 font-mono tabular-nums">{(d.confidence * 100).toFixed(0)}%</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{REGIME_LABEL[d.regime.label]}</td>
                  <td className="px-4 py-2.5 font-mono tabular-nums">{d.expectedRR?.toFixed(1) ?? "—"}</td>
                  <td className="max-w-xs truncate px-4 py-2.5 text-muted-foreground">{d.strategy.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
      <SignalDetail d={open} open={!!open} onOpenChange={(v) => !v && setOpen(null)} />
    </div>
  );
}

function IndexCard({ symbol }: { symbol: string }) {
  const q = useAura((s) => s.quotes[symbol]);
  const bars = barsOf(symbol, "1D");
  if (!q) return null;
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{symbol}</div>
            <div className="mt-1 font-mono text-2xl tabular-nums">
              <Price value={q.ltp} />
            </div>
            <div className="mt-1 text-sm">
              <Signed value={q.changePct} pct />
              <span className="ml-2 text-muted-foreground">Vol {formatVolume(q.volume)}</span>
            </div>
          </div>
          <Sparkline bars={bars} className="h-10 w-24" />
        </div>
      </CardContent>
    </Card>
  );
}
