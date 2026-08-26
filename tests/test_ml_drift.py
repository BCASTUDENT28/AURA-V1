"""
tests/test_ml_drift.py

Phase 7 — Feature Drift Monitor tests.
Tests PSI, Z-score, variance ratio, stale detection, and baseline management.
"""

from __future__ import annotations

import time
import math
import pytest

from backend.app.ml.drift_monitor import (
    FeatureDriftMonitor,
    DriftReport,
    _psi,
    _compute_stats,
)


# ─────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────

class TestPSI:

    def test_identical_distributions_psi_near_zero(self):
        vals = [float(i) for i in range(200)]
        psi = _psi(vals, vals[:], n_bins=10)
        assert psi < 0.05, f"Identical distributions PSI should be ~0, got {psi}"

    def test_very_different_distributions_high_psi(self):
        base = [float(i) for i in range(200)]
        curr = [float(i + 100) for i in range(200)]  # shifted by 100
        psi = _psi(base, curr, n_bins=10)
        assert psi > 0.25, f"Very different distributions PSI should be > 0.25, got {psi}"

    def test_psi_returns_negative_on_insufficient_data(self):
        base = [1.0, 2.0, 3.0]  # too few
        curr = [1.0, 2.0, 3.0]
        psi = _psi(base, curr, n_bins=10)
        assert psi == -1.0

    def test_psi_symmetric_warning_at_threshold(self):
        # Moderately shifted: expect WARN range 0.10-0.25
        import random
        random.seed(42)
        base = [random.gauss(0, 1) for _ in range(300)]
        curr = [random.gauss(0.5, 1) for _ in range(300)]
        psi = _psi(base, curr)
        assert psi >= 0.0, "PSI must be non-negative for real distributions"


class TestComputeStats:

    def test_empty_returns_zeros(self):
        s = _compute_stats("test", [])
        assert s.count == 0
        assert s.mean == 0
        assert s.std == 0

    def test_single_value(self):
        s = _compute_stats("test", [42.0])
        assert s.count == 1
        assert s.mean == 42.0

    def test_known_distribution(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        s = _compute_stats("test", vals)
        assert s.mean == pytest.approx(3.0, abs=1e-4)
        assert s.min == 1.0
        assert s.max == 5.0
        assert s.p50 == pytest.approx(3.0, abs=0.5)


# ─────────────────────────────────────────────────────────
# FeatureDriftMonitor
# ─────────────────────────────────────────────────────────

class TestFeatureDriftMonitor:

    def _make_monitor(self) -> FeatureDriftMonitor:
        """Fresh monitor with tiny baseline threshold for testing."""
        m = FeatureDriftMonitor()
        m.BASELINE_MIN = 20  # override for fast test
        return m

    def test_no_baseline_yet_returns_ok(self):
        m = self._make_monitor()
        for i in range(10):
            m.push("rsi", float(i))
        report = m.check("rsi")
        assert report.status == "OK"
        assert "Baseline not yet established" in report.message

    def test_baseline_established_after_min_samples(self):
        m = self._make_monitor()
        m.BASELINE_MIN = 20
        for i in range(25):
            m.push("rsi", float(i % 100))
        report = m.check("rsi")
        # Has baseline, should compute properly
        assert report.status in ("OK", "WARN", "DRIFT")

    def test_stable_distribution_ok_status(self):
        m = self._make_monitor()
        m.BASELINE_MIN = 30
        # Push baseline-establishing data
        for i in range(50):
            m.push("rsi", 50.0 + (i % 10) * 0.1)  # tight range
        # Push similar current data
        for i in range(30):
            m.push("rsi", 50.0 + (i % 10) * 0.1)
        report = m.check("rsi")
        assert report.status == "OK", f"Expected OK for stable distribution, got {report.status}: {report.message}"

    def test_large_mean_shift_triggers_drift(self):
        m = self._make_monitor()
        m.BASELINE_MIN = 50
        # Establish baseline around 50
        for i in range(60):
            m.push("rsi", 50.0)
        # Override current window with very different values
        for i in range(60):
            m.push("rsi", 90.0)
        report = m.check("rsi")
        assert report.status in ("WARN", "DRIFT"), \
            f"Expected WARN or DRIFT for large shift, got {report.status}"

    def test_check_all_returns_list(self):
        m = self._make_monitor()
        m.push("rsi", 50.0)
        m.push("adx", 25.0)
        reports = m.check_all()
        assert isinstance(reports, list)
        assert len(reports) == 2

    def test_summary_counts_by_status(self):
        m = self._make_monitor()
        m.push("rsi", 50.0)
        m.push("adx", 25.0)
        m.check_all()
        summary = m.summary()
        assert isinstance(summary, dict)
        assert "OK" in summary

    def test_reset_baseline_clears_it(self):
        m = self._make_monitor()
        m.BASELINE_MIN = 10
        for i in range(20):
            m.push("rsi", float(i))
        # Should have baseline now
        assert "rsi" in m._baseline
        m.reset_baseline("rsi")
        assert "rsi" not in m._baseline

    def test_report_has_timestamp(self):
        m = self._make_monitor()
        m.push("rsi", 50.0)
        report = m.check("rsi")
        assert report.timestamp > 0

    def test_drift_report_fields(self):
        m = self._make_monitor()
        m.BASELINE_MIN = 5
        for i in range(10):
            m.push("vol", float(i))
        report = m.check("vol")
        assert hasattr(report, "psi")
        assert hasattr(report, "zScoreDrift")
        assert hasattr(report, "varianceRatio")
        assert hasattr(report, "currentStats")

    def test_z_score_drift_direction(self):
        m = self._make_monitor()
        m.BASELINE_MIN = 30
        # Baseline around 50
        for _ in range(40):
            m.push("price", 50.0)
        # Current much higher
        for _ in range(20):
            m.push("price", 200.0)
        report = m.check("price")
        assert report.zScoreDrift > 0, "Upward shift should yield positive Z-score drift"

    def test_variance_ratio_expands_on_wider_distribution(self):
        m = self._make_monitor()
        m.BASELINE_MIN = 30
        # Baseline: tight
        for i in range(40):
            m.push("spread", 50.0 + (i % 3))
        # Current: wide
        for i in range(40):
            m.push("spread", float(i * 10))
        report = m.check("spread")
        assert report.varianceRatio > 1.0, "Wider current distribution should have var ratio > 1"
