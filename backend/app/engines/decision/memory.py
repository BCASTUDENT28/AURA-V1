"""
backend/app/engines/decision/memory.py

Port of src/lib/aura/memory.ts
In Phase 1, learnings come from the client (passed in via the API request body).
The backend does not persist learnings independently in Phase 1.
"""

from __future__ import annotations

from backend.app.schemas.types import Learning, RegimeLabel


def aggregate_learnings(items: list[Learning]) -> list[Learning]:
    """Group by (strategyId, regime, kind) and average R-multiples."""
    from collections import defaultdict
    groups: dict[str, list[Learning]] = defaultdict(list)
    for it in items:
        k = f"{it.strategyId}|{it.regime}|{it.kind}"
        groups[k].append(it)

    out: list[Learning] = []
    for k, arr in groups.items():
        n = len(arr)
        avg_r = sum(it.rMultiple or 0 for it in arr) / n
        latest = arr[0]
        out.append(Learning(
            **{**latest.model_dump(), **{
                "id": f"agg-{k}",
                "sampleSize": n,
                "confidence": min(0.75, 0.2 + n * 0.06),
                "evidence": f"{n} paper outcomes · avg R {avg_r:.2f} · {latest.setup}",
                "rMultiple": avg_r,
            }}
        ))
    return sorted(out, key=lambda x: -x.sampleSize)


def flag_from_memory(
    learnings: list[Learning],
    strategy_id: str,
    regime: RegimeLabel,
) -> Learning | None:
    agg = aggregate_learnings(learnings)
    for l in agg:
        if (
            l.strategyId == strategy_id
            and l.regime == regime
            and l.kind == "FAILURE"
            and l.sampleSize >= 5
        ):
            return l
    return None


def get_learnings(symbol: str) -> list[Learning]:
    """
    Phase 1: no persistent storage. Returns empty list.
    Phase 2+ will query the DB by symbol.
    """
    return []
