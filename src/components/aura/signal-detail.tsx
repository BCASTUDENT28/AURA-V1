import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { computeIndicators } from "@/lib/aura/indicators";
import { getInstrument } from "@/lib/aura/instruments";
import { barsOf } from "@/lib/aura/market";
import { ACTION_LABEL, REGIME_LABEL, formatPct } from "@/lib/aura/format";
import type { Decision } from "@/lib/aura/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { ActionChip, Price } from "@/components/aura/price";
import { OrderTicket } from "@/components/aura/order-ticket";
import { CandleChart } from "@/components/aura/candle-chart";
import { STRATEGY_BY_ID } from "@/lib/aura/strategies";

export function SignalDetail({
  d,
  open,
  onOpenChange,
}: {
  d: Decision | null;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  if (!d) return null;
  const inst = getInstrument(d.symbol);
  const bars = barsOf(d.symbol, "1D");
  const ind = computeIndicators(bars);
  const strat = STRATEGY_BY_ID[d.strategy.strategyId];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle className="pr-8">
          {inst.symbol}
          <span className="ml-2 text-sm font-normal text-muted-foreground">{inst.name}</span>
        </DialogTitle>
        <DialogDescription>
          Signal is not a decision. Decision is not certainty. Risk can still veto.
        </DialogDescription>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <ActionChip action={d.action} />
          <Badge variant="outline">{REGIME_LABEL[d.regime.label]}</Badge>
          <Badge variant="outline">Conf {(d.confidence * 100).toFixed(0)}%</Badge>
          <Badge variant="outline">{d.risk}</Badge>
          {d.expectedRR != null && <Badge variant="outline">R:R {d.expectedRR.toFixed(1)}</Badge>}
        </div>
        <div className="mt-4 h-40 overflow-hidden rounded-lg bg-muted">
          <CandleChart bars={bars} />
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <Prob label="Up" v={d.probabilityUp} tone="text-up" />
          <Prob label="Neutral" v={d.probabilityNeutral} />
          <Prob label="Down" v={d.probabilityDown} tone="text-down" />
        </div>
        <Separator className="my-4" />
        <section className="grid gap-3 text-sm">
          <Row k="Strategy" v={`${strat?.name ?? d.strategy.strategyId} ${d.strategy.version}`} />
          <Row k="Entry" v={d.entry ? <Price value={d.entry} /> : "—"} />
          <Row k="Stop" v={d.stop ? <Price value={d.stop} /> : "—"} />
          <Row k="Target" v={d.target ? <Price value={d.target} /> : "—"} />
          <Row k="Invalidation" v={d.invalidation} />
          <Row
            k="Similarity"
            v={
              d.similar.n
                ? `${d.similar.n} matches · win ${formatPct(d.similar.winRate, 0)} · avg ${formatPct(d.similar.avgReturn)} · MAE ${formatPct(d.similar.avgMae)}`
                : "Insufficient neighbors"
            }
          />
        </section>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <List title="Evidence" items={d.reasons.map((e) => e.text)} tone="up" />
          <List title="Contradictions" items={d.contradictions.map((e) => e.text)} tone="down" />
        </div>
        {d.riskReasons.length > 0 && (
          <div className="mt-3 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
            Risk veto: {d.riskReasons.join(" ")}
          </div>
        )}
        <p className="mt-3 font-mono text-[10px] text-muted-foreground">
          {d.lineage.strategyVersion} · {d.lineage.modelVersion} · {d.lineage.featureVersion} · {d.lineage.datasetVersion} · {d.lineage.costVersion}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          RSI {ind.rsi.toFixed(0)} · ADX {ind.adx.toFixed(1)} · VWAP {ind.vwap.toFixed(2)} · RV {(ind.realizedVol * 100).toFixed(1)}%
        </p>
        <Separator className="my-4" />
        <div className="grid gap-4 md:grid-cols-2">
          <OrderTicket
            symbol={d.symbol}
            side={d.action === "SELL" ? "SELL" : "BUY"}
            suggested={d.entry ?? undefined}
            stop={d.stop}
            target={d.target}
            strategyId={d.strategy.strategyId}
          />
          <div className="flex flex-col justify-end gap-2">
            <Button variant="outline" asChild>
              <Link to="/research" search={{ symbol: d.symbol }}>
                Open research desk
              </Link>
            </Button>
            <Button variant="ghost" asChild>
              <Link to="/lab" search={{ symbol: d.symbol, strategy: d.strategy.strategyId }}>
                Backtest this strategy
              </Link>
            </Button>
            <p className="text-[11px] text-muted-foreground">
              {ACTION_LABEL[d.action]} is a paper suggestion. Live path is sealed.
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Prob({ label, v, tone }: { label: string; v: number; tone?: string }) {
  return (
    <div className="rounded-lg bg-muted px-2 py-3">
      <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
      <div className={`mt-1 font-mono text-lg tabular-nums ${tone ?? ""}`}>{(v * 100).toFixed(0)}%</div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-3">
      <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{k}</div>
      <div className="text-sm">{v}</div>
    </div>
  );
}

function List({ title, items, tone }: { title: string; items: string[]; tone: "up" | "down" }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{title}</div>
      <ul className="mt-2 grid gap-1.5">
        {items.map((t) => (
          <li key={t} className="flex gap-2 text-sm">
            <span className={tone === "up" ? "text-up" : "text-down"}>—</span>
            <span>{t}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
