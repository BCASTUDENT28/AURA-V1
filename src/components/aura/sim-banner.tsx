import type { ReactNode } from "react";
import { activeProvider } from "@/lib/aura/provider";
import { LIVE_EXECUTION_ENABLED } from "@/lib/aura/broker";
import { cn } from "@/lib/utils";

export function SimBanner({
  className,
  children,
}: {
  className?: string;
  children?: ReactNode;
}) {
  return (
    <div
      className={cn(
        "min-w-0 rounded-xl bg-warn/10 px-4 py-3 text-sm leading-relaxed text-warn",
        className,
      )}
    >
      {children ??
        `${activeProvider.disclaimer} Live execution ${LIVE_EXECUTION_ENABLED ? "is on" : "is sealed"}.`}
    </div>
  );
}
