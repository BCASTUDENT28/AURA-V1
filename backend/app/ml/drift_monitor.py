"""
backend/app/ml/drift_monitor.py

Feature Drift Monitor for AURA AI (Phase 7).

Tracks statistical drift of a named feature over a rolling window compared
to a baseline distribution.  Used to detect model degradation and trigger
re-calibration alerts.

Drift Detection Methods:
  1. Population Stability Index (PSI) — binned distribution comparison
  2. Z-Score Drift — rolling mean shift relative to baseline std
  3. Variance Ratio — current / baseline variance (Levene-style)

Output:
  - DriftReport per feature with actionable status: OK | WARN | DRIFT | STALE
  - PSI score (industry standard: <0.1 OK, 0.1-0.25 WARN, >0.25 DRIFT)
  - Optional alert emission via event bus
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from typing import Optional

from pydantic import BaseModel


class FeatureStats(BaseModel):
    name: str
    count: int
    mean: float
    std: float
    min: float
    max: float
    p25: float
    p50: float
    p75: float


class DriftReport(BaseModel):
    feature: str
    status: str          # "OK" | "WARN" | "DRIFT" | "STALE"
    psi: float
    zScoreDrift: float   # (current_mean - baseline_mean) / baseline_std
    varianceRatio: float # current_std^2 / baseline_std^2
    currentStats: FeatureStats
    baselineStats: Optional[FeatureStats]
    message: str
    timestamp: float


def _percentile(sorted_data: list[float], pct: float) -> float:
    if not sorted_data:
        return 0.0
    n = len(sorted_data)
    idx = pct / 100.0 * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    return sorted_data[lo] + (idx - lo) * (sorted_data[hi] - sorted_data[lo])


def _compute_stats(name: str, values: list[float]) -> FeatureStats:
    if not values:
        return FeatureStats(name=name, count=0, mean=0, std=0, min=0, max=0,
                             p25=0, p50=0, p75=0)
    s = sorted(values)
    n = len(s)
    mean = sum(s) / n
    variance = sum((x - mean) ** 2 for x in s) / max(n - 1, 1)
    std = math.sqrt(variance)
    return FeatureStats(
        name=name, count=n, mean=round(mean, 6), std=round(std, 6),
        min=round(s[0], 6), max=round(s[-1], 6),
        p25=round(_percentile(s, 25), 6),
        p50=round(_percentile(s, 50), 6),
        p75=round(_percentile(s, 75), 6),
    )


def _psi(baseline_vals: list[float], current_vals: list[float], n_bins: int = 10) -> float:
    """Population Stability Index via equal-frequency binning on baseline."""
    if len(baseline_vals) < n_bins or len(current_vals) < 5:
        return -1.0  # Insufficient data

    s_base = sorted(baseline_vals)
    n_b = len(s_base)
    # Equal-frequency bin edges from baseline
    edges: list[float] = []
    for i in range(1, n_bins):
        idx = int(i * n_b / n_bins)
        edges.append(s_base[idx])
    edges = [-math.inf] + edges + [math.inf]

    def bucket_counts(vals: list[float]) -> list[int]:
        counts = [0] * n_bins
        for v in vals:
            for j in range(n_bins):
                if edges[j] < v <= edges[j + 1]:
                    counts[j] += 1
                    break
        return counts

    b_counts = bucket_counts(baseline_vals)
    c_counts = bucket_counts(current_vals)
    n_c = len(current_vals)

    psi_sum = 0.0
    for bc, cc in zip(b_counts, c_counts):
        p_b = max(bc / n_b, 1e-6)
        p_c = max(cc / n_c, 1e-6)
        psi_sum += (p_c - p_b) * math.log(p_c / p_b)

    return round(psi_sum, 5)


class FeatureDriftMonitor:
    """
    Tracks incoming feature values and raises drift alerts
    when the current distribution shifts relative to baseline.
    """

    BASELINE_MIN = 120   # minimum samples before establishing baseline
    WINDOW_SIZE = 500    # rolling current window size
    PSI_WARN = 0.10
    PSI_DRIFT = 0.25
    ZSCORE_WARN = 2.0
    ZSCORE_DRIFT = 3.0
    VAR_RATIO_WARN = 2.0
    VAR_RATIO_DRIFT = 4.0
    STALE_SECS = 3600    # 1 hour without new data

    def __init__(self) -> None:
        self._baseline: dict[str, list[float]] = {}
        self._current: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self.WINDOW_SIZE)
        )
        self._last_seen: dict[str, float] = {}
        self._reports: dict[str, DriftReport] = {}

    def push(self, feature: str, value: float) -> None:
        """Ingest a new observation for a feature."""
        self._current[feature].append(value)
        self._last_seen[feature] = time.time()

        # Promote to baseline on first fill
        if feature not in self._baseline and len(self._current[feature]) >= self.BASELINE_MIN:
            self._baseline[feature] = list(self._current[feature])

    def check(self, feature: str) -> DriftReport:
        """Compute drift report for a single feature."""
        now = time.time()
        current_vals = list(self._current.get(feature, []))
        baseline_vals = self._baseline.get(feature)
        last_t = self._last_seen.get(feature, 0)

        # Stale check
        if (now - last_t) > self.STALE_SECS and current_vals:
            cur_stats = _compute_stats(feature, current_vals)
            return DriftReport(
                feature=feature, status="STALE", psi=-1.0,
                zScoreDrift=0.0, varianceRatio=1.0,
                currentStats=cur_stats, baselineStats=None,
                message=f"No new data for {self.STALE_SECS}s",
                timestamp=now
            )

        cur_stats = _compute_stats(feature, current_vals)

        if not baseline_vals:
            return DriftReport(
                feature=feature, status="OK", psi=-1.0,
                zScoreDrift=0.0, varianceRatio=1.0,
                currentStats=cur_stats, baselineStats=None,
                message=f"Baseline not yet established (n={cur_stats.count}/{self.BASELINE_MIN})",
                timestamp=now
            )

        base_stats = _compute_stats(feature, baseline_vals)

        psi = _psi(baseline_vals, current_vals)
        baseline_std = max(base_stats.std, 1e-9)
        z_drift = (cur_stats.mean - base_stats.mean) / baseline_std
        var_ratio = (cur_stats.std ** 2) / max(base_stats.std ** 2, 1e-12)

        # Status classification
        if psi > self.PSI_DRIFT or abs(z_drift) > self.ZSCORE_DRIFT or var_ratio > self.VAR_RATIO_DRIFT:
            status = "DRIFT"
            msg = f"CRITICAL drift — PSI={psi:.3f}, Z={z_drift:.2f}, VarRatio={var_ratio:.2f}"
        elif psi > self.PSI_WARN or abs(z_drift) > self.ZSCORE_WARN or var_ratio > self.VAR_RATIO_WARN:
            status = "WARN"
            msg = f"Drift warning — PSI={psi:.3f}, Z={z_drift:.2f}, VarRatio={var_ratio:.2f}"
        else:
            status = "OK"
            msg = f"Stable — PSI={psi:.3f}, Z={z_drift:.2f}, VarRatio={var_ratio:.2f}"

        report = DriftReport(
            feature=feature, status=status, psi=psi,
            zScoreDrift=round(z_drift, 4),
            varianceRatio=round(var_ratio, 4),
            currentStats=cur_stats, baselineStats=base_stats,
            message=msg, timestamp=now
        )
        self._reports[feature] = report
        return report

    def check_all(self) -> list[DriftReport]:
        """Check all tracked features."""
        return [self.check(f) for f in self._current.keys()]

    def reset_baseline(self, feature: str) -> None:
        """Explicitly reset baseline for re-calibration after market regime shift."""
        if feature in self._baseline:
            del self._baseline[feature]

    def summary(self) -> dict[str, int]:
        """Count of reports by status."""
        counts: dict[str, int] = {"OK": 0, "WARN": 0, "DRIFT": 0, "STALE": 0}
        for r in self._reports.values():
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts


# Singleton monitor shared across the app
_MONITOR = FeatureDriftMonitor()


def get_drift_monitor() -> FeatureDriftMonitor:
    return _MONITOR
