import { createFileRoute } from "@tanstack/react-router";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatIst } from "@/lib/aura/format";
import { aggregateLearnings } from "@/lib/aura/memory";
import { useAura } from "@/store/aura-store";

export const Route = createFileRoute("/memory")({ component: MemoryPage });

function MemoryPage() {
  const items = useAura((s) => s.learnings);
  const agg = aggregateLearnings(items);

  return (
    <div className="mx-auto grid max-w-7xl gap-4">
      <div>
        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Trade memory</p>
        <h1 className="mt-1 text-2xl font-medium tracking-tight">Learnings</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Written only from paper outcomes on this desk — not seeded, not scraped, not imagined. A learning is a
          hypothesis with a sample size and an expiry. Flags stay dark until n ≥ 5. Lineage ids (strategy / model /
          feature / dataset) are stored with each close.
        </p>
      </div>
      {items.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Empty on purpose. Close a paper trade and the outcome lands here. Until then there is nothing honest to
            remember.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-2">
            {agg.map((l) => (
              <Card key={l.id}>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between gap-2">
                    <span className="truncate">{l.setup}</span>
                    <span className={`text-xs ${l.kind === "SUCCESS" ? "text-up" : "text-down"}`}>{l.kind}</span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm">{l.evidence}</p>
                  <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                    n={l.sampleSize} · conf {(l.confidence * 100).toFixed(0)}% · expires {formatIst(l.expiresTs, false)}
                    {l.sampleSize < 5 ? " · flag gated" : ""}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Raw ledger</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2">
              {items.slice(0, 20).map((l) => (
                <div key={l.id} className="flex flex-wrap items-baseline justify-between gap-2 border-t border-border py-2 text-sm">
                  <span>{l.evidence}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">{formatIst(l.ts)}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
