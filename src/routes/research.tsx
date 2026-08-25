import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { ActionChip } from "@/components/aura/price";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { reviewSetup } from "@/lib/aura/ai";
import { computeIndicators } from "@/lib/aura/indicators";
import { getInstrument } from "@/lib/aura/instruments";
import { barsOf } from "@/lib/aura/market";
import { REGIME_LABEL, formatPct } from "@/lib/aura/format";
import { useAura } from "@/store/aura-store";

type Search = { symbol?: string };

export const Route = createFileRoute("/research")({
  validateSearch: (s: Record<string, unknown>): Search => ({
    symbol: typeof s.symbol === "string" ? s.symbol : undefined,
  }),
  component: ResearchPage,
});

function ResearchPage() {
  const search = Route.useSearch();
  const signals = useAura((s) => s.signals);
  const [symbol, setSymbol] = useState(search.symbol ?? signals[0]?.symbol ?? "NIFTY");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const d = signals.find((x) => x.symbol === symbol) ?? signals[0];

  const run = async () => {
    if (!d) return;
    setBusy(true);
    setErr(null);
    const inst = getInstrument(d.symbol);
    const ind = computeIndicators(barsOf(d.symbol, "1D"));
    const res = await reviewSetup({
      data: {
        symbol: d.symbol,
        name: inst.name,
        action: d.action,
        confidence: d.confidence,
        regime: d.regime.label,
        regimeNotes: d.regime.notes,
        strategy: `${d.strategy.strategyId}@${d.strategy.version}`,
        strategyReason: d.strategy.reason,
        invalidation: d.invalidation,
        similar: d.similar.n
          ? `n=${d.similar.n}, win ${formatPct(d.similar.winRate, 0)}, avg ${formatPct(d.similar.avgReturn)}`
          : "insufficient sample",
        evidence: d.reasons.map((e) => e.text),
        contradictions: d.contradictions.map((e) => e.text),
        risk: d.risk,
        indicators: `RSI ${ind.rsi.toFixed(1)}, ADX ${ind.adx.toFixed(1)}, VWAP ${ind.vwap.toFixed(2)}, RV ${(ind.realizedVol * 100).toFixed(1)}%, relVol ${ind.relVolume.toFixed(2)}`,
        lineage: `${d.lineage.strategyVersion} / ${d.lineage.modelVersion} / ${d.lineage.datasetVersion}`,
      },
    });
    setBusy(false);
    if (!res.ok) {
      setErr(res.error);
      toast.error(res.error);
      return;
    }
    setNote(res.text);
  };

  return (
    <div className="mx-auto grid max-w-3xl gap-4">
      <div>
        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Explainer, not a signal</p>
        <h1 className="mt-1 text-2xl font-medium tracking-tight">Research desk</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          The model is handed numbers this desk already computed. It may not invent prices, edges, or orders. User
          initiated — never on page load.
        </p>
      </div>
      {d && (
        <Card>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              <select
                className="h-8 rounded-md bg-secondary px-2 text-sm"
                value={d.symbol}
                onChange={(e) => setSymbol(e.target.value)}
              >
                {signals.map((s) => (
                  <option key={s.symbol} value={s.symbol}>
                    {s.symbol}
                  </option>
                ))}
              </select>
              <ActionChip action={d.action} />
              <span className="text-sm font-normal text-muted-foreground">
                {REGIME_LABEL[d.regime.label]} · {(d.confidence * 100).toFixed(0)}%
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <p className="text-sm">{d.strategy.reason}</p>
            <ul className="grid gap-1 text-sm text-muted-foreground">
              {d.contradictions.slice(0, 3).map((c) => (
                <li key={c.text}>— {c.text}</li>
              ))}
            </ul>
            <Button onClick={run} disabled={busy}>
              {busy ? "Reading the file…" : "Ask the research desk"}
            </Button>
          </CardContent>
        </Card>
      )}
      {err && <p className="text-sm text-down">{err}</p>}
      {note && (
        <Card>
          <CardHeader>
            <CardTitle>Note</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="whitespace-pre-wrap text-sm leading-relaxed">{note}</div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
