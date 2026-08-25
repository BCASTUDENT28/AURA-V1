import { cn } from "@/lib/utils";

export function Label({ className, ...props }: React.ComponentProps<"label">) {
  return (
    <label
      className={cn("text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground", className)}
      {...props}
    />
  );
}
