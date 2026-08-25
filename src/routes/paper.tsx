import { createFileRoute } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { OrderTicket } from "@/components/aura/order-ticket";
import { Price, Signed } from "@/components/aura/price";
import { SimBanner } from "@/components/aura/sim-banner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatInr, formatIst } from "@/lib/aura/format";
import { INSTRUMENTS } from "@/lib/aura/instruments";
import { navOf, unrealizedOf } from "@/lib/aura/paper";
import { useAura } from "@/store/aura-store";

export const Route = createFileRoute("/paper")({ component: PaperPage });

function PaperPage() {
  const book = useAura((s) => s.book);
  const quotes = useAura((s) => s.quotes);
  const flatten = useAura((s) => s.flatten);
  const reset = useAura((s) => s.resetPaper);
  const sessionId = useAura((s) => s.sessionId);
  const persistSource = useAura((s) => s.persistSource);
  const costNote = useAura((s) => s.costNote);
  const [sym, setSym] = useState("RELIANCE");
  const nav = navOf(book, quotes);
  const u = unrealizedOf(book, quotes);

  return (
    <div className="mx-auto grid max-w-7xl gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Simulator</p>
          <h1 className="mt-1 text-2xl font-medium tracking-tight">Paper trading</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Limit orders only. Stops required. Fills pay brokerage, STT, stamp, GST and 2 bps slippage. This book never
            talks to a broker. Reset archives the session — it does not delete history.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => {
              flatten();
              toast.message("Flattened all paper positions.");
            }}
          >
            Flatten
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              reset();
              toast.message("Paper book reset to ₹10 L.");
            }}
          >
            Reset book
          </Button>
        </div>
      </div>
      <SimBanner>
        {persistSource === "postgres"
          ? `Ledger source of truth: Postgres · session ${sessionId ?? "—"}.`
          : persistSource === "syncing"
            ? "Syncing paper book to the ledger…"
            : "Ledger unreachable — using local cache. Fills still never hit a broker."}{" "}
        {costNote ?? ""}
      </SimBanner>
      <div className="grid gap-3 md:grid-cols-4">
        <Stat k="NAV" v={formatInr(nav)} />
        <Stat k="Cash" v={formatInr(book.cash)} />
        <Stat k="Unrealized" v={<Signed value={u} />} />
        <Stat k="Realized" v={<Signed value={book.realized} />} />
      </div>
      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Ticket</CardTitle>
            <select className="h-8 rounded-md bg-secondary px-2 text-xs" value={sym} onChange={(e) => setSym(e.target.value)}>
              {INSTRUMENTS.map((i) => (
                <option key={i.symbol} value={i.symbol}>
                  {i.symbol}
                </option>
              ))}
            </select>
          </CardHeader>
          <CardContent>
            <OrderTicket symbol={sym} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Positions</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto p-0">
            {book.positions.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">No open paper positions.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-left text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 font-medium">Symbol</th>
                    <th className="px-4 py-2 font-medium">Side</th>
                    <th className="px-4 py-2 font-medium">Qty</th>
                    <th className="px-4 py-2 font-medium">Avg</th>
                    <th className="px-4 py-2 font-medium">LTP</th>
                    <th className="px-4 py-2 font-medium">P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {book.positions.map((p) => {
                    const ltp = quotes[p.symbol]?.ltp ?? p.avgPrice;
                    const dir = p.side === "BUY" ? 1 : -1;
                    const pnl = dir * (ltp - p.avgPrice) * p.qty;
                    return (
                      <tr key={p.symbol} className="border-t border-border">
                        <td className="px-4 py-2 font-medium">{p.symbol}</td>
                        <td className="px-4 py-2">{p.side}</td>
                        <td className="px-4 py-2 font-mono tabular-nums">{p.qty}</td>
                        <td className="px-4 py-2 font-mono tabular-nums">
                          <Price value={p.avgPrice} />
                        </td>
                        <td className="px-4 py-2 font-mono tabular-nums">
                          <Price value={ltp} />
                        </td>
                        <td className="px-4 py-2">
                          <Signed value={pnl} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Blotter</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          {book.orders.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">No orders yet.</p>
          ) : (
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">Time</th>
                  <th className="px-4 py-2 font-medium">Symbol</th>
                  <th className="px-4 py-2 font-medium">Side</th>
                  <th className="px-4 py-2 font-medium">Qty</th>
                  <th className="px-4 py-2 font-medium">Limit</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Costs</th>
                </tr>
              </thead>
              <tbody>
                {book.orders.slice(0, 30).map((o) => (
                  <tr key={o.id} className="border-t border-border">
                    <td className="px-4 py-2 text-xs text-muted-foreground">{formatIst(o.ts)}</td>
                    <td className="px-4 py-2">{o.symbol}</td>
                    <td className="px-4 py-2">{o.side}</td>
                    <td className="px-4 py-2 font-mono tabular-nums">{o.qty}</td>
                    <td className="px-4 py-2 font-mono tabular-nums">{o.limitPrice.toFixed(2)}</td>
                    <td className="px-4 py-2">
                      {o.status}
                      {o.rejectReason ? <span className="block text-[11px] text-down">{o.rejectReason}</span> : null}
                    </td>
                    <td className="px-4 py-2 font-mono tabular-nums">{o.costs ? o.costs.total.toFixed(0) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
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
