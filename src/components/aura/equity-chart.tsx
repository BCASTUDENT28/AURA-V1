import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatInrCompact } from "@/lib/aura/format";

export function EquityChart({ data }: { data: { t: number; v: number }[] }) {
  const rows = data.map((d) => ({
    t: new Date(d.t).toISOString().slice(0, 10),
    v: Math.round(d.v),
  }));
  const up = (rows[rows.length - 1]?.v ?? 0) >= (rows[0]?.v ?? 0);
  const color = up ? "#5dba87" : "#d4676f";
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.28} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="t" hide />
          <YAxis hide domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{
              background: "#14171d",
              border: "1px solid #23262e",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(v: number) => [formatInrCompact(v), "Equity"]}
          />
          <Area type="monotone" dataKey="v" stroke={color} fill="url(#eq)" strokeWidth={1.6} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
