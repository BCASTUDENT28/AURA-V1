import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getInstrument } from "@/lib/aura/instruments";
import { formatPrice } from "@/lib/aura/format";
import { useAura } from "@/store/aura-store";

export function OrderTicket({
  symbol,
  side,
  suggested,
  stop,
  target,
  strategyId,
}: {
  symbol: string;
  side?: "BUY" | "SELL";
  suggested?: number;
  stop?: number | null;
  target?: number | null;
  strategyId?: string | null;
}) {
  const quote = useAura((s) => s.quotes[symbol]);
  const place = useAura((s) => s.place);
  const [qty, setQty] = useState("10");
  const [limit, setLimit] = useState("");
  const [stopPx, setStopPx] = useState(stop ? String(stop.toFixed(2)) : "");
  const [tgt, setTgt] = useState(target ? String(target.toFixed(2)) : "");
  const [act, setAct] = useState<"BUY" | "SELL">(side ?? "BUY");
  const inst = getInstrument(symbol);
  const px = suggested ?? quote?.ltp ?? inst.base;
  const limitPx = Number(limit || px);

  const submit = async () => {
    const q = Math.floor(Number(qty));
    const res = await place({
      symbol,
      side: act,
      qty: q,
      limitPrice: limitPx,
      stop: stopPx ? Number(stopPx) : null,
      target: tgt ? Number(tgt) : null,
      strategyId: strategyId ?? null,
    });
    if (res.ok) toast.success(res.message);
    else toast.error(res.message);
  };

  return (
    <div className="grid gap-3">
      <div className="flex gap-1 rounded-lg bg-secondary p-1">
        <button
          type="button"
          onClick={() => setAct("BUY")}
          className={`h-9 flex-1 rounded-md text-xs font-medium ${act === "BUY" ? "bg-up text-background" : "text-muted-foreground"}`}
        >
          Buy
        </button>
        <button
          type="button"
          onClick={() => setAct("SELL")}
          className={`h-9 flex-1 rounded-md text-xs font-medium ${act === "SELL" ? "bg-down text-white" : "text-muted-foreground"}`}
        >
          Sell
        </button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1.5">
          <Label>Quantity</Label>
          <Input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="numeric" />
        </div>
        <div className="grid gap-1.5">
          <Label>Limit</Label>
          <Input value={limit} placeholder={formatPrice(px)} onChange={(e) => setLimit(e.target.value)} />
        </div>
        <div className="grid gap-1.5">
          <Label>Stop</Label>
          <Input value={stopPx} onChange={(e) => setStopPx(e.target.value)} placeholder="Required" />
        </div>
        <div className="grid gap-1.5">
          <Label>Target</Label>
          <Input value={tgt} onChange={(e) => setTgt(e.target.value)} />
        </div>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Limit only · paper · Indian cost model applied on fill. Risk engine can reject.
      </p>
      <Button onClick={submit} variant={act === "BUY" ? "up" : "down"} className="w-full">
        Paper {act.toLowerCase()} {inst.symbol}
      </Button>
    </div>
  );
}
