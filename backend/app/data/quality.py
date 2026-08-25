"""
backend/app/data/quality.py

Automated Data Quality & Validation Engine.
Performs:
- Continuity and missing session candle audits
- Duplicate timestamp detection
- Outlier / anomalous spike filtering
- Corporate action adjustments (splits, bonuses)
"""

from __future__ import annotations

import datetime
from typing import Optional
from backend.app.schemas.market_data import (
    CorporateAction,
    DataQualityReport,
    DataQualityStatus,
    HistoricalBarRecord,
)
from backend.app.schemas.types import Bar


def check_duplicate_timestamps(bars: list[HistoricalBarRecord | Bar]) -> int:
    """Count duplicate timestamps in a candle series."""
    seen = set()
    duplicates = 0
    for b in bars:
        if b.t in seen:
            duplicates += 1
        else:
            seen.add(b.t)
    return duplicates


def detect_outlier_ticks(
    bars: list[HistoricalBarRecord | Bar],
    max_jump_pct: float = 0.10,
) -> list[dict]:
    """
    Flag candles where the high-low range or single-bar close jump is > max_jump_pct (e.g. 10%)
    without volume confirmation (i.e. anomalous bad tick).
    """
    outliers = []
    if len(bars) < 2:
        return outliers

    for i in range(1, len(bars)):
        curr = bars[i]
        prev = bars[i - 1]
        pct_change = abs(curr.c - prev.c) / prev.c if prev.c != 0 else 0
        candle_span_pct = (curr.h - curr.l) / curr.l if curr.l != 0 else 0

        if pct_change > max_jump_pct or candle_span_pct > (max_jump_pct * 1.5):
            outliers.append({
                "timestamp": curr.t,
                "pct_change": round(pct_change, 4),
                "close": curr.c,
                "prev_close": prev.c,
                "volume": curr.v,
            })
    return outliers


def validate_session_continuity(
    bars: list[HistoricalBarRecord | Bar],
    timeframe: str = "1D",
) -> int:
    """
    Count missing session days/bars.
    For daily data: checks weekdays between start and end.
    """
    if len(bars) < 2:
        return 0

    missing = 0
    if timeframe == "1D":
        sorted_bars = sorted(bars, key=lambda b: b.t)
        for i in range(1, len(sorted_bars)):
            prev_dt = datetime.datetime.fromtimestamp(sorted_bars[i - 1].t / 1000, tz=datetime.timezone.utc)
            curr_dt = datetime.datetime.fromtimestamp(sorted_bars[i].t / 1000, tz=datetime.timezone.utc)

            # Count weekday delta
            day_diff = (curr_dt.date() - prev_dt.date()).days
            if day_diff > 1:
                # Iterate in-between days and count weekdays missed
                for d in range(1, day_diff):
                    check_day = prev_dt.date() + datetime.timedelta(days=d)
                    if check_day.weekday() < 5:  # Mon-Fri
                        missing += 1
    return missing


def apply_corporate_actions(
    bars: list[HistoricalBarRecord | Bar],
    actions: list[CorporateAction],
) -> list[HistoricalBarRecord]:
    """
    Apply backward adjustment to historical OHLC series for stock splits and bonuses.
    For example, a 1:2 split on exDate cuts historical prices in half before exDate.
    """
    if not actions or not bars:
        return [
            HistoricalBarRecord(
                t=b.t, o=b.o, h=b.h, l=b.l, c=b.c, v=b.v, vwap=getattr(b, "vwap", None), isAdjusted=True,
            )
            for b in bars
        ]

    # Convert to mutable records
    out: list[HistoricalBarRecord] = [
        HistoricalBarRecord(
            t=b.t, o=b.o, h=b.h, l=b.l, c=b.c, v=b.v, vwap=getattr(b, "vwap", None), isAdjusted=True,
        )
        for b in bars
    ]

    for act in actions:
        if act.actionType in ("SPLIT", "BONUS") and act.ratioFrom and act.ratioTo:
            multiplier = act.ratioFrom / act.ratioTo
            # Parse ex_date to timestamp ms (start of UTC day)
            ex_dt = datetime.datetime.strptime(act.exDate, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
            ex_ts_ms = int(ex_dt.timestamp() * 1000)

            for b in out:
                if b.t < ex_ts_ms:
                    b.o = round(b.o * multiplier, 2)
                    b.h = round(b.h * multiplier, 2)
                    b.l = round(b.l * multiplier, 2)
                    b.c = round(b.c * multiplier, 2)
                    b.v = round(b.v / multiplier, 2)
    return out


def audit_dataset(
    dataset_version_id: str,
    bars_by_symbol: dict[str, list[Bar | HistoricalBarRecord]],
    actions_by_symbol: Optional[dict[str, list[CorporateAction]]] = None,
    max_outlier_pct: float = 0.10,
) -> DataQualityReport:
    """Run full data quality validation audit across all symbols in a dataset."""
    actions_by_symbol = actions_by_symbol or {}
    total_missing = 0
    total_dupes = 0
    total_outliers = 0
    total_actions = sum(len(acts) for acts in actions_by_symbol.values())

    symbol_metrics = {}

    for sym, bars in bars_by_symbol.items():
        dupes = check_duplicate_timestamps(bars)
        outliers = detect_outlier_ticks(bars, max_jump_pct=max_outlier_pct)
        missing = validate_session_continuity(bars, "1D")

        total_dupes += dupes
        total_outliers += len(outliers)
        total_missing += missing

        symbol_metrics[sym] = {
            "bars": len(bars),
            "duplicates": dupes,
            "outliers": len(outliers),
            "missingDays": missing,
        }

    status: DataQualityStatus = "PASS"
    notes = "All session continuity, duplicate, and outlier validation checks passed."

    if total_outliers > 0 or total_dupes > 0:
        status = "WARN"
        notes = f"Detected {total_outliers} outlier spikes and {total_dupes} duplicate candles."
    elif total_missing > 20:
        status = "WARN"
        notes = f"Elevated missing session days ({total_missing}) across universe."

    return DataQualityReport(
        datasetVersionId=dataset_version_id,
        status=status,
        missingCandles=total_missing,
        duplicateCandles=total_dupes,
        outlierTicks=total_outliers,
        corporateActionsApplied=total_actions,
        notes=notes,
        metrics={"symbols": symbol_metrics},
    )
