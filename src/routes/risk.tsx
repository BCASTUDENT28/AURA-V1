import { createFileRoute } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { formatInr, formatPct } from "@/lib/aura/format";
import { DEFAULT_LIMITS } from "@/lib/aura/risk";
import { useAura } from "@/store/aura-store";

export const Route = createFileRoute("/risk")({ component: RiskPage });

function RiskPage() {
  const risk = useAura((s) => s.riskSnap);
  const kill = useAura((s) => s.killSwitch);
  const setKill = useAura((s) => s.setKill);
  const flatten = useAura((s) => s.flatten);

  const rows = [
    { k: "Environment", v: "PAPER", ok: true, note: "Live credentials are not loaded. Live path is sealed." },
    { k: "Live path", v: risk.livePathSealed ? "SEALED" : "open", ok: risk.livePathSealed, note: "BrokerExecutionInterface always refuses. Angel One is Phase 9." },
    { k: "Data source", v: risk.dataSource, ok: true, note: "Simulator. Not NSE. Do not treat tape as evidence of edge." },
    { k: "Kill switch", v: kill ? "ARMED" : "off", ok: !kill, note: "Overrides every signal. AI cannot disarm it." },
    { k: "Daily loss", v: formatPct(risk.dailyPnlPct), ok: risk.dailyPnlPct > -DEFAULT_LIMITS.maxDailyLossPct, note: `Breaker at −${(DEFAULT_LIMITS.maxDailyLossPct * 100).toFixed(0)}%.` },
    { k: "Exposure", v: formatPct(risk.exposurePct, 1), ok: risk.exposurePct <= DEFAULT_LIMITS.maxExposurePct, note: `Cap ${(DEFAULT_LIMITS.maxExposurePct * 100).toFixed(0)}% of NAV.` },
    { k: "Open positions", v: String(risk.openPositions), ok: risk.openPositions < DEFAULT_LIMITS.maxPositions, note: `Max ${DEFAULT_LIMITS.maxPositions}.` },
    { k: "Order type", v: "LIMIT only", ok: true, note: "NSE: algo orders cannot be Market or IOC." },
    { k: "OPS throttle", v: `${DEFAULT_LIMITS.opsPerSec}/sec`, ok: true, note: "Angel One enforces 9/sec, one under the NSE 10 OPS line." },
    { k: "Data freshness", v: `${Math.round(risk.dataAgeMs)} ms`, ok: risk.dataAgeMs <= DEFAULT_LIMITS.dataFreshMs, note: "Stale tape cannot become a signal." },
    { k: "Static IP", v: risk.staticIpOk ? "paper exemption" : "missing", ok: risk.staticIpOk, note: "Paper path is exempt. Live adapter must never pass true without a verified IP." },
    { k: "Stop-loss", v: "required", ok: true, note: "Ticket without a stop is rejected." },
  ];

  return (
    <div className="mx-auto grid max-w-7xl gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Hard gates</p>
          <h1 className="mt-1 text-2xl font-medium tracking-tight">Risk engine</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            If risk fails, the final decision is SKIP. No model, committee, or prompt can override that without a
            system-level change — which this desk will not do.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex h-10 items-center gap-2 text-sm">
            Kill switch
            <Switch checked={kill} onCheckedChange={setKill} />
          </label>
          <Button variant="outline" onClick={flatten}>
            Flatten book
          </Button>
        </div>
      </div>
      {!risk.canTrade && (
        <div className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Trading blocked. {risk.breaches.join(" ")}
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        {rows.map((r) => (
          <Card key={r.k}>
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-3">
                <span>{r.k}</span>
                <span className={`text-xs font-medium ${r.ok ? "text-up" : "text-down"}`}>{r.ok ? "PASS" : "FAIL"}</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="font-mono text-lg tabular-nums">{r.v}</div>
              <p className="mt-2 text-sm text-muted-foreground">{r.note}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Day P&L vs breaker</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="font-mono text-2xl tabular-nums">{formatInr(risk.dailyPnl, true)}</div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
            <div
              className={`h-full ${risk.dailyPnl >= 0 ? "bg-up" : "bg-down"}`}
              style={{ width: `${Math.min(100, (Math.abs(risk.dailyPnlPct) / DEFAULT_LIMITS.maxDailyLossPct) * 100)}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Bar fills as you approach the −2% daily loss circuit.</p>
        </CardContent>
      </Card>
    </div>
  );
}
