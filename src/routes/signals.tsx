import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { ActionChip, Price } from "@/components/aura/price";
import { SignalDetail } from "@/components/aura/signal-detail";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getInstrument } from "@/lib/aura/instruments";
import { REGIME_LABEL } from "@/lib/aura/format";
import type { Action, Decision } from "@/lib/aura/types";
import { useAura } from "@/store/aura-store";

export const Route = createFileRoute("/signals")({ component: SignalsPage });

const FILTERS: (Action | "ALL")[] = ["ALL", "BUY", "SELL", "HOLD", "SKIP"];

function SignalsPage() {
  const signals = useAura((s) => s.signals);
  const quotes = useAura((s) => s.quotes);
  const [q, setQ] = useState("");
  const [f, setF] = useState<Action | "ALL">("ALL");
  const [open, setOpen] = useState<Decision | null>(null);
  const rows = useMemo(
    () =>
      signals.filter((d) => {
        if (f !== "ALL" && d.action !== f) return false;
        const inst = getInstrument(d.symbol);
        const hay = `${d.symbol} ${inst.name} ${inst.sector}`.toLowerCase();
        return hay.includes(q.toLowerCase());
      }),
    [signals, q, f],
  );

  return (
    <div className="mx-auto grid max-w-7xl gap-4">
      <div>
        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Decision board</p>
        <h1 className="mt-1 text-2xl font-medium tracking-tight">Signals</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Each row is a versioned strategy output, a regime, a similarity sample, and a risk tag. Click through for
          evidence and contradictions. Nothing here is a live order.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter symbol or sector"
          className="max-w-xs"
        />
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((x) => (
            <button
              key={x}
              type="button"
              onClick={() => setF(x)}
              className={`h-10 rounded-md px-3 text-xs ${f === x ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground"}`}
            >
              {x}
            </button>
          ))}
        </div>
      </div>
      <Card>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="text-left text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Symbol</th>
                <th className="px-4 py-3 font-medium">LTP</th>
                <th className="px-4 py-3 font-medium">Action</th>
                <th className="px-4 py-3 font-medium">Conf</th>
                <th className="px-4 py-3 font-medium">P(up)</th>
                <th className="px-4 py-3 font-medium">Risk</th>
                <th className="px-4 py-3 font-medium">Strategy</th>
                <th className="px-4 py-3 font-medium">Regime</th>
                <th className="px-4 py-3 font-medium">Similar</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => {
                const inst = getInstrument(d.symbol);
                const px = quotes[d.symbol];
                return (
                  <tr
                    key={d.id}
                    className="cursor-pointer border-t border-border hover:bg-accent/40"
                    onClick={() => setOpen(d)}
                  >
                    <td className="px-4 py-2.5">
                      <div className="font-medium">{d.symbol}</div>
                      <div className="text-[11px] text-muted-foreground">{inst.sector}</div>
                    </td>
                    <td className="px-4 py-2.5 font-mono tabular-nums">
                      <Price value={px?.ltp ?? 0} />
                    </td>
                    <td className="px-4 py-2.5">
                      <ActionChip action={d.action} />
                    </td>
                    <td className="px-4 py-2.5 font-mono tabular-nums">{(d.confidence * 100).toFixed(0)}%</td>
                    <td className="px-4 py-2.5 font-mono tabular-nums">{(d.probabilityUp * 100).toFixed(0)}%</td>
                    <td className="px-4 py-2.5 text-xs">{d.risk}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{d.strategy.strategyId}@ {d.strategy.version}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{REGIME_LABEL[d.regime.label]}</td>
                    <td className="px-4 py-2.5 font-mono text-xs tabular-nums">
                      n={d.similar.n} · {(d.similar.winRate * 100).toFixed(0)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>
      <SignalDetail d={open} open={!!open} onOpenChange={(v) => !v && setOpen(null)} />
    </div>
  );
}
