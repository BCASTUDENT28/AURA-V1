import type { Learning, PaperPosition, Quote, RegimeLabel } from "./types";
import { DATASET_VERSION, FEATURE_VERSION, MODEL_VERSION } from "./types";

let n = 1;

export function recordClose(args: {
  position: PaperPosition;
  exit: number;
  now: number;
  regime: RegimeLabel;
}): Learning {
  const dir = args.position.side === "BUY" ? 1 : -1;
  const pnl = dir * (args.exit - args.position.avgPrice) * args.position.qty;
  const risk = Math.abs(args.position.avgPrice - (args.position.stop ?? args.position.avgPrice * 0.99)) * args.position.qty;
  const r = risk ? pnl / risk : 0;
  const kind: Learning["kind"] = r >= 0 ? "SUCCESS" : "FAILURE";
  const setup = `${args.position.strategyId ?? "discretionary"} · ${args.position.side} · ${args.regime}`;
  return {
    id: `mem-${args.now}-${n++}`,
    ts: args.now,
    kind,
    setup,
    strategyId: args.position.strategyId ?? "discretionary",
    strategyVersion: "v1",
    modelVersionId: `model:${MODEL_VERSION}`,
    featureVersionId: `feature:${FEATURE_VERSION}`,
    datasetVersionId: `dataset:${DATASET_VERSION}`,
    minSampleRequired: 5,
    regime: args.regime,
    symbol: args.position.symbol,
    evidence: `${args.position.symbol} closed at ${args.exit.toFixed(2)} vs avg ${args.position.avgPrice.toFixed(2)} · R=${r.toFixed(2)}`,
    sampleSize: 1,
    confidence: 0.25,
    expiresTs: args.now + 90 * 86400000,
    rMultiple: r,
  };
}

export function aggregateLearnings(items: Learning[]): Learning[] {
  const map = new Map<string, Learning[]>();
  for (const it of items) {
    const k = `${it.strategyId}|${it.regime}|${it.kind}`;
    const arr = map.get(k) ?? [];
    arr.push(it);
    map.set(k, arr);
  }
  const out: Learning[] = [];
  for (const [k, arr] of map) {
    const n = arr.length;
    const avgR = arr.reduce((a, x) => a + (x.rMultiple ?? 0), 0) / n;
    const latest = arr[0]!;
    out.push({
      ...latest,
      id: `agg-${k}`,
      sampleSize: n,
      confidence: Math.min(0.75, 0.2 + n * 0.06),
      evidence: `${n} paper outcomes · avg R ${avgR.toFixed(2)} · ${latest.setup}`,
      rMultiple: avgR,
    });
  }
  return out.sort((a, b) => b.sampleSize - a.sampleSize);
}

export function flagFromMemory(
  learnings: Learning[],
  strategyId: string,
  regime: RegimeLabel,
): Learning | null {
  const agg = aggregateLearnings(learnings).find(
    (l) => l.strategyId === strategyId && l.regime === regime && l.kind === "FAILURE" && l.sampleSize >= 5,
  );
  return agg ?? null;
}

export function hydrateQuote(_q: Quote): void {
  /* placeholder to keep imports honest */
}
