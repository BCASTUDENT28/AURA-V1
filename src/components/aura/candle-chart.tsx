import type { Bar } from "@/lib/aura/types";
import { cn } from "@/lib/utils";

export function CandleChart({
  bars,
  className,
  count = 72,
}: {
  bars: Bar[];
  className?: string;
  count?: number;
}) {
  const slice = bars.slice(-count);
  if (slice.length < 2) return null;
  const w = 640;
  const h = 220;
  const pad = { t: 12, r: 12, b: 18, l: 8 };
  const highs = slice.map((b) => b.h);
  const lows = slice.map((b) => b.l);
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const span = max - min || 1;
  const cw = (w - pad.l - pad.r) / slice.length;
  const y = (px: number) => pad.t + ((max - px) / span) * (h - pad.t - pad.b);
  const last = slice[slice.length - 1]!;
  const first = slice[0]!;
  const up = last.c >= first.o;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={cn("h-full w-full", className)} role="img" aria-label="Price chart">
      <line x1={pad.l} x2={w - pad.r} y1={y(last.c)} y2={y(last.c)} stroke="currentColor" strokeOpacity={0.12} strokeDasharray="3 4" />
      {slice.map((b, i) => {
        const x = pad.l + i * cw + cw / 2;
        const bull = b.c >= b.o;
        const color = bull ? "#5dba87" : "#d4676f";
        const bodyTop = y(Math.max(b.o, b.c));
        const bodyBot = y(Math.min(b.o, b.c));
        const bh = Math.max(1.2, bodyBot - bodyTop);
        return (
          <g key={b.t}>
            <line x1={x} x2={x} y1={y(b.h)} y2={y(b.l)} stroke={color} strokeWidth={1} />
            <rect x={x - Math.max(1.4, cw * 0.32)} y={bodyTop} width={Math.max(2.8, cw * 0.64)} height={bh} fill={color} />
          </g>
        );
      })}
      <text x={w - pad.r} y={y(last.c) - 4} textAnchor="end" fill={up ? "#5dba87" : "#d4676f"} fontSize="11" fontFamily="IBM Plex Mono, ui-monospace, monospace">
        {last.c.toFixed(2)}
      </text>
    </svg>
  );
}

export function Sparkline({ bars, className }: { bars: Bar[]; className?: string }) {
  const slice = bars.slice(-40);
  if (slice.length < 2) return null;
  const w = 120;
  const h = 36;
  const min = Math.min(...slice.map((b) => b.l));
  const max = Math.max(...slice.map((b) => b.h));
  const span = max - min || 1;
  const d = slice
    .map((b, i) => {
      const x = (i / (slice.length - 1)) * w;
      const y = ((max - b.c) / span) * (h - 4) + 2;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  const up = slice[slice.length - 1]!.c >= slice[0]!.c;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={cn("overflow-visible", className)} aria-hidden>
      <path d={d} fill="none" stroke={up ? "#5dba87" : "#d4676f"} strokeWidth="1.5" />
    </svg>
  );
}
