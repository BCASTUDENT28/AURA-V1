import { createFileRoute } from "@tanstack/react-router";
import { SimBanner } from "@/components/aura/sim-banner";
import { Card, CardContent } from "@/components/ui/card";
import { formatIst } from "@/lib/aura/format";
import { NEWS_DISCLAIMER } from "@/lib/aura/news";
import { useAura } from "@/store/aura-store";

export const Route = createFileRoute("/news")({ component: NewsPage });

function NewsPage() {
  const news = useAura((s) => s.news);
  return (
    <div className="mx-auto grid max-w-7xl gap-4">
      <div>
        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Context</p>
        <h1 className="mt-1 text-2xl font-medium tracking-tight">News & sentiment</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{NEWS_DISCLAIMER}</p>
      </div>
      <SimBanner>
        SAMPLE. These headlines are hardcoded with fake timestamps. Do not treat them as market intelligence.
      </SimBanner>
      <div className="grid gap-3">
        {news.map((n) => (
          <Card key={n.id}>
            <CardContent className="flex flex-col gap-2 p-4 md:flex-row md:items-start md:justify-between">
              <div className="min-w-0">
                <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                  {n.source} · {n.event} · {n.impact}
                </div>
                <h2 className="mt-1 text-base font-medium tracking-tight">{n.headline}</h2>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {n.symbols.map((s) => (
                    <span key={s} className="rounded-full bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div
                  className={`font-mono text-sm tabular-nums ${n.sentiment > 0.05 ? "text-up" : n.sentiment < -0.05 ? "text-down" : "text-muted-foreground"}`}
                >
                  {n.sentiment > 0 ? "+" : ""}
                  {n.sentiment.toFixed(2)}
                </div>
                <div className="text-[11px] text-muted-foreground">{formatIst(n.ts)}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
