import { formatNum, formatPct, formatPrice } from "@/lib/aura/format";
import { cn } from "@/lib/utils";

export function Signed({
  value,
  pct = false,
  className,
}: {
  value: number;
  pct?: boolean;
  className?: string;
}) {
  const tone = value > 1e-9 ? "text-up" : value < -1e-9 ? "text-down" : "text-muted-foreground";
  return (
    <span className={cn("font-mono tabular-nums", tone, className)}>
      {pct ? formatPct(value) : `${value > 0 ? "+" : ""}${formatNum(value)}`}
    </span>
  );
}

export function Price({ value, className }: { value: number; className?: string }) {
  return <span className={cn("font-mono tabular-nums", className)}>{formatPrice(value)}</span>;
}

export function ActionChip({ action }: { action: string }) {
  const map: Record<string, string> = {
    BUY: "bg-up/15 text-up",
    SELL: "bg-down/15 text-down",
    HOLD: "bg-secondary text-muted-foreground",
    SKIP: "bg-warn/15 text-warn",
  };
  return (
    <span className={cn("inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium", map[action] ?? map.HOLD)}>
      {action}
    </span>
  );
}
