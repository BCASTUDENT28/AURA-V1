import { createFileRoute } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Signed } from "@/components/aura/price";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatInr, formatPct } from "@/lib/aura/format";
import { getInstrument } from "@/lib/aura/instruments";
import { navOf, unrealizedOf } from "@/lib/aura/paper";
import { useAura } from "@/store/aura-store";

export const Route = createFileRoute("/portfolio")({ component: PortfolioPage });

const COLORS = ["#c5ccd6", "#5dba87", "#8b8e96", "#d4676f", "#9aa8bc", "#c4a35a", "#6e7a88"];

function PortfolioPage() {
  const book = useAura((s) => s.book);
  const quotes = useAura((s) => s.quotes);
  const nav = navOf(book, quotes);
  const u = unrealizedOf(book, quotes);
  const risk = useAura((s) => s.riskSnap);

  const holdings = book.positions.map((p) => {
    const ltp = quotes[p.symbol]?.ltp ?? p.avgPrice;
    const value = Math.abs(p.qty * ltp);
    const dir = p.side === "BUY" ? 1 : -1;
    const pnl = dir * (ltp - p.avgPrice) * p.qty;
    return { ...p, ltp, value, pnl, sector: getInstrument(p.symbol).sector };
  });
  const bySector = new Map<string, number>();
  for (const h of holdings) bySector.set(h.sector, (bySector.get(h.sector) ?? 0) + h.value);
  const pie = [
    { name: "Cash", value: Math.max(0, book.cash) },
    ...[...bySector.entries()].map(([name, value]) => ({ name, value })),
  ];

  return (
    <div className="mx-auto grid max-w-7xl gap-4">
      <div>
        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Book</p>
        <h1 className="mt-1 text-2xl font-medium tracking-tight">Portfolio</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          A trade is only interesting if the rest of the book can absorb it. Concentration and correlation sit above
          any single signal.
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <Stat k="NAV" v={formatInr(nav)} />
        <Stat k="Cash" v={formatInr(book.cash)} />
        <Stat k="Unrealized" v={<Signed value={u} />} />
        <Stat k="Exposure" v={formatPct(risk.exposurePct, 1)} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Allocation</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pie} dataKey="value" nameKey="name" innerRadius={58} outerRadius={88} paddingAngle={2}>
                  {pie.map((e, i) => (
                    <Cell key={e.name} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: "#14171d", border: "1px solid #23262e", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number, n: string) => [formatInr(v), n]}
                />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Holdings</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto p-0">
            {holdings.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">Cash only. Open a paper position from Signals or Paper.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-left text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 font-medium">Symbol</th>
                    <th className="px-4 py-2 font-medium">Sector</th>
                    <th className="px-4 py-2 font-medium">Value</th>
                    <th className="px-4 py-2 font-medium">Weight</th>
                    <th className="px-4 py-2 font-medium">P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h) => (
                    <tr key={h.symbol} className="border-t border-border">
                      <td className="px-4 py-2">{h.symbol}</td>
                      <td className="px-4 py-2 text-muted-foreground">{h.sector}</td>
                      <td className="px-4 py-2 font-mono tabular-nums">{formatInr(h.value)}</td>
                      <td className="px-4 py-2 font-mono tabular-nums">{formatPct(h.value / nav, 1)}</td>
                      <td className="px-4 py-2">
                        <Signed value={h.pnl} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Stat({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="rounded-xl bg-card p-4 shadow-[var(--shadow-border)]">
      <div className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{k}</div>
      <div className="mt-1 font-mono text-xl tabular-nums">{v}</div>
    </div>
  );
}
