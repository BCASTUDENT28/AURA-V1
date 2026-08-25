import type { ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  BookOpen,
  ClipboardList,
  Ellipsis,
  FlaskConical,
  LayoutDashboard,
  Newspaper,
  NotebookPen,
  Shield,
  Sparkles,
  Wallet,
} from "lucide-react";
import { useEffect } from "react";
import { Toaster } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { formatInrCompact, formatIst, formatPct } from "@/lib/aura/format";
import { cn } from "@/lib/utils";
import { useAura } from "@/store/aura-store";
import { Signed } from "./price";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/signals", label: "Signals", icon: Activity },
  { to: "/lab", label: "Strategy lab", icon: FlaskConical },
  { to: "/paper", label: "Paper", icon: NotebookPen },
  { to: "/portfolio", label: "Portfolio", icon: Wallet },
  { to: "/risk", label: "Risk", icon: Shield },
  { to: "/memory", label: "Memory", icon: BookOpen },
  { to: "/news", label: "News", icon: Newspaper },
  { to: "/research", label: "Research", icon: Sparkles },
  { to: "/gap", label: "Gap report", icon: ClipboardList },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const hydrate = useAura((s) => s.hydrate);
  const tick = useAura((s) => s.tick);
  const now = useAura((s) => s.now);
  const nifty = useAura((s) => s.quotes.NIFTY);
  const bank = useAura((s) => s.quotes.BANKNIFTY);
  const kill = useAura((s) => s.killSwitch);
  const setKill = useAura((s) => s.setKill);
  const nav = useAura((s) => s.nav());
  const persistSource = useAura((s) => s.persistSource);
  const daily = useAura((s) => s.book.dailyPnl);

  useEffect(() => {
    hydrate();
    const id = window.setInterval(() => tick(), 1000);
    return () => window.clearInterval(id);
  }, [hydrate, tick]);

  return (
    <TooltipProvider delayDuration={200}>
      <div className="tape min-h-dvh overflow-x-hidden bg-background text-foreground">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-card focus:p-3">
          Skip to content
        </a>
        <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur-sm">
          <div className="flex items-center gap-3 px-3 py-2 lg:px-5">
            <Link to="/" className="flex items-center gap-2 pr-2">
              <span className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <svg viewBox="0 0 32 32" className="size-5" aria-hidden>
                  <rect x="15" y="4" width="2" height="5" fill="currentColor" />
                  <rect x="8" y="9" width="6" height="18" fill="currentColor" />
                  <rect x="18" y="9" width="6" height="18" fill="currentColor" />
                  <rect x="8" y="16" width="16" height="4" fill="currentColor" />
                </svg>
              </span>
              <span className="leading-tight">
                <span className="block text-sm font-semibold tracking-[0.18em]">AURA</span>
                <span className="hidden text-[10px] uppercase tracking-[0.16em] text-muted-foreground sm:block">
                  Paper desk
                </span>
              </span>
            </Link>
            <Badge variant="paper">PAPER</Badge>
            <Badge variant="sim" className="hidden min-[380px]:inline-flex">
              SIMULATED
            </Badge>
            <div className="hidden items-center gap-4 md:flex">
              <Tape symbol="NIFTY" q={nifty} />
              <Tape symbol="BANKNIFTY" q={bank} />
            </div>
            <div className="ml-auto flex items-center gap-3">
              <div className="hidden text-right sm:block">
                <div className="font-mono text-xs tabular-nums">{formatInrCompact(nav)}</div>
                <div className="text-[10px] text-muted-foreground">
                  Day <Signed value={daily / 1_000_000} pct />
                </div>
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <label className="flex h-10 items-center gap-2 rounded-md px-2 hover:bg-accent">
                    <span className="hidden text-[11px] uppercase tracking-[0.12em] text-muted-foreground lg:inline">
                      Kill
                    </span>
                    <Switch checked={kill} onCheckedChange={setKill} aria-label="Kill switch" />
                  </label>
                </TooltipTrigger>
                <TooltipContent>Halts all new paper orders. Positions stay until you flatten.</TooltipContent>
              </Tooltip>
              <div className="hidden font-mono text-[11px] tabular-nums text-muted-foreground lg:block">
                {formatIst(now)} IST
              </div>
            </div>
          </div>
        </header>

        <div className="flex">
          <aside className="sticky top-[53px] hidden h-[calc(100dvh-53px)] w-52 shrink-0 flex-col border-r border-border p-3 lg:flex">
            <nav className="grid gap-0.5">
              {NAV.map((item) => {
                const active = item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={cn(
                      "flex h-10 items-center gap-2.5 rounded-lg px-2.5 text-sm",
                      active ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                    )}
                  >
                    <Icon className="size-4" />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
            <p className="mt-auto px-2 pt-6 text-[11px] leading-relaxed text-muted-foreground">
              Simulated Indian cash tape. Ledger is Postgres. No live orders. No return guarantee. Risk engine has veto.
              {persistSource === "postgres" ? " Book synced." : persistSource === "syncing" ? " Syncing ledger…" : " Local cache only."}
            </p>
          </aside>

          <main id="main" className="min-w-0 flex-1 overflow-x-hidden px-3 py-4 pb-24 lg:px-6 lg:pb-8">
            {children}
          </main>
        </div>

        <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background/95 pb-[env(safe-area-inset-bottom)] lg:hidden">
          <div className="grid grid-cols-5">
            {[
              NAV[0],
              NAV[1],
              NAV[2],
              NAV[3],
              { to: "/more", label: "More", icon: Ellipsis },
            ].map((item) => {
              const active = item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
              const Icon = item.icon;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    "flex min-h-14 flex-col items-center justify-center gap-1 text-[10px]",
                    active ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  <Icon className="size-4" />
                  {item.label.replace("Strategy lab", "Lab")}
                </Link>
              );
            })}
          </div>
        </nav>
        <Toaster theme="dark" position="bottom-right" />
      </div>
    </TooltipProvider>
  );
}

function Tape({ symbol, q }: { symbol: string; q?: { ltp: number; changePct: number } }) {
  if (!q) return null;
  return (
    <div className="flex items-baseline gap-2 font-mono text-xs tabular-nums">
      <span className="text-muted-foreground">{symbol}</span>
      <span>{q.ltp.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>
      <span className={q.changePct >= 0 ? "text-up" : "text-down"}>{formatPct(q.changePct)}</span>
    </div>
  );
}
