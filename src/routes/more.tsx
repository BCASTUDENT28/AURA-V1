import { createFileRoute, Link } from "@tanstack/react-router";
import { BookOpen, ClipboardList, Newspaper, Shield, Sparkles } from "lucide-react";

export const Route = createFileRoute("/more")({ component: MorePage });

const ITEMS = [
  { to: "/risk", label: "Risk engine", copy: "Hard gates, kill switch, 9 OPS, limit-only.", icon: Shield },
  { to: "/memory", label: "Memory", copy: "Learnings from paper outcomes only.", icon: BookOpen },
  { to: "/news", label: "News", copy: "SAMPLE headlines. Does not trade.", icon: Newspaper },
  { to: "/research", label: "Research desk", copy: "LLM explainer over computed evidence.", icon: Sparkles },
  { to: "/gap", label: "Gap report", copy: "KEEP / MODIFY / REWRITE freeze for every file.", icon: ClipboardList },
] as const;

function MorePage() {
  return (
    <div className="mx-auto grid max-w-lg gap-3">
      <h1 className="text-2xl font-medium tracking-tight">Desk</h1>
      {ITEMS.map((it) => {
        const Icon = it.icon;
        return (
          <Link
            key={it.to}
            to={it.to}
            className="flex min-h-16 items-center gap-3 rounded-xl bg-card px-4 py-3 shadow-[var(--shadow-border)]"
          >
            <Icon className="size-5 text-muted-foreground" />
            <span>
              <span className="block text-sm font-medium">{it.label}</span>
              <span className="block text-xs text-muted-foreground">{it.copy}</span>
            </span>
          </Link>
        );
      })}
    </div>
  );
}
