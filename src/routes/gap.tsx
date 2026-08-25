import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  GAP_BUILD,
  GAP_FILES,
  GAP_KEEP,
  GAP_MODIFY,
  GAP_PHASES,
  GAP_PLATFORM,
  GAP_PRINCIPLES,
  GAP_REMOVE,
  GAP_REWRITE,
  GAP_SCORES,
  type GapVerdict,
} from "@/lib/aura/gap";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/gap")({ component: GapPage });

const FILTERS: { id: GapVerdict | "ALL"; label: string; n: number }[] = [
  { id: "ALL", label: "All", n: GAP_FILES.length },
  { id: "KEEP", label: "Keep", n: GAP_KEEP.length },
  { id: "MODIFY", label: "Modify", n: GAP_MODIFY.length },
  { id: "REWRITE", label: "Rewrite", n: GAP_REWRITE.length },
  { id: "REMOVE", label: "Remove", n: GAP_REMOVE.length },
  { id: "BUILD NEW", label: "Build new", n: GAP_BUILD.length },
  { id: "PLATFORM", label: "Platform", n: GAP_PLATFORM.length },
];

function GapPage() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("ALL");
  const rows = useMemo(
    () => (filter === "ALL" ? GAP_FILES : GAP_FILES.filter((f) => f.verdict === filter)),
    [filter],
  );

  return (
    <div className="mx-auto grid max-w-7xl gap-4">
      <div>
        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Freeze</p>
        <h1 className="mt-1 text-2xl font-medium tracking-tight">Grok → AURA production gap</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Prototype V0.1 is the reference desk. This page is the file-level freeze: what we keep, what we
          change, and what we will not build yet. Live trading is not on the table.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {(
          [
            ["UI / product", GAP_SCORES.ui],
            ["Quant prototype", GAP_SCORES.quant],
            ["Research engine", GAP_SCORES.research],
            ["ML system", GAP_SCORES.ml],
            ["Prod infra", GAP_SCORES.production],
            ["Safety", GAP_SCORES.safety],
          ] as const
        ).map(([k, v]) => (
          <Card key={k}>
            <CardContent className="p-4">
              <div className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{k}</div>
              <div className="mt-1 font-mono text-2xl tabular-nums">{v}/10</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Rules of the freeze</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2">
          {GAP_PRINCIPLES.map((p) => (
            <p key={p} className="border-t border-border pt-2 text-sm leading-relaxed first:border-t-0 first:pt-0">
              {p}
            </p>
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-3 md:grid-cols-2">
        {GAP_PHASES.map((p) => (
          <Card key={p.id}>
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-2">
                <span>{p.title}</span>
                <span
                  className={cn(
                    "text-[11px] uppercase tracking-[0.12em]",
                    p.status === "done" && "text-up",
                    p.status === "now" && "text-warn",
                    p.status === "next" && "text-muted-foreground",
                  )}
                >
                  {p.status === "done" ? "Done" : p.status === "now" ? "This cut" : "Later"}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed text-muted-foreground">{p.body}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className={cn(
              "h-10 rounded-full px-3 text-xs",
              filter === f.id ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground",
            )}
          >
            {f.label} {f.n}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>File freeze · {rows.length}</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="text-left text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">File</th>
                <th className="px-4 py-2 font-medium">Verdict</th>
                <th className="px-4 py-2 font-medium">When</th>
                <th className="px-4 py-2 font-medium">Why</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((f) => (
                <tr key={f.path} className="border-t border-border align-top">
                  <td className="px-4 py-2.5 font-mono text-xs">{f.path}</td>
                  <td className="px-4 py-2.5">
                    <Verdict v={f.verdict} />
                  </td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">{f.phase}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{f.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function Verdict({ v }: { v: GapVerdict }) {
  const cls =
    v === "KEEP"
      ? "text-up"
      : v === "MODIFY"
        ? "text-warn"
        : v === "REWRITE"
          ? "text-down"
          : v === "REMOVE"
            ? "text-down"
            : v === "BUILD NEW"
              ? "text-foreground"
              : "text-muted-foreground";
  return <span className={cn("text-[11px] font-medium uppercase tracking-[0.12em]", cls)}>{v}</span>;
}
