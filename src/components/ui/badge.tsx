import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium tracking-wide",
  {
    variants: {
      variant: {
        default: "bg-secondary text-muted-foreground",
        outline: "shadow-[var(--shadow-border)] text-muted-foreground",
        buy: "bg-up/15 text-up",
        sell: "bg-down/15 text-down",
        hold: "bg-secondary text-muted-foreground",
        skip: "bg-warn/15 text-warn",
        paper: "bg-primary/10 text-primary",
        sim: "bg-warn/15 text-warn",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant, className }))} {...props} />;
}
