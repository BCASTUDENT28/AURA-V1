"""
tests/test_ml_calibration.py

Phase 7 — Probability Calibration tests.
Tests Platt Scaling (gradient descent) and Isotonic Regression (PAV).
"""

from __future__ import annotations

import math
import pytest

from backend.app.ml.calibration import (
    PlattCalibrator,
    IsotonicCalibrator,
    get_calibrator,
    list_calibrators,
)


# ─────────────────────────────────────────────────────────
# Platt Calibrator
# ─────────────────────────────────────────────────────────

class TestPlattCalibrator:

    def test_identity_before_fit(self):
        """Before MIN_FIT_SAMPLES, calibrate() must return raw_prob unchanged."""
        cal = PlattCalibrator("test_platt")
        for p in [0.1, 0.5, 0.9]:
            assert cal.calibrate(p) == p

    def test_state_not_ready_before_fit(self):
        cal = PlattCalibrator("test_state")
        assert cal.state.isReady is False
        assert cal.state.nFit == 0

    def test_fit_requires_min_samples(self):
        cal = PlattCalibrator("test_fit")
        for i in range(30):  # below MIN_FIT_SAMPLES=50
            cal.record(0.6, 1)
        result = cal.fit()
        assert result is False

    def test_fit_succeeds_with_enough_samples(self):
        cal = PlattCalibrator("test_enough")
        # 60 positives at prob 0.8, 60 negatives at prob 0.2
        for _ in range(60):
            cal.record(0.8, 1)
            cal.record(0.2, 0)
        result = cal.fit()
        assert result is True
        assert cal.state.isReady is True

    def test_calibrated_prob_in_0_1(self):
        cal = PlattCalibrator("test_range")
        for _ in range(60):
            cal.record(0.8, 1)
            cal.record(0.2, 0)
        cal.fit()
        for raw in [0.1, 0.3, 0.5, 0.7, 0.9]:
            c = cal.calibrate(raw)
            assert 0.0 <= c <= 1.0, f"Calibrated prob {c} out of range for raw {raw}"

    def test_monotonic_calibration(self):
        """Higher raw prob should calibrate to higher calibrated prob."""
        cal = PlattCalibrator("test_mono")
        for _ in range(60):
            cal.record(0.8, 1)
            cal.record(0.2, 0)
        cal.fit()
        probs = [0.1, 0.3, 0.5, 0.7, 0.9]
        calibrated = [cal.calibrate(p) for p in probs]
        for i in range(len(calibrated) - 1):
            assert calibrated[i] < calibrated[i + 1], \
                f"Non-monotonic: cal({probs[i]})={calibrated[i]} >= cal({probs[i+1]})={calibrated[i+1]}"

    def test_state_reflects_nfit(self):
        cal = PlattCalibrator("test_nfit")
        for _ in range(30):
            cal.record(0.5, 1)
        assert cal.state.nFit == 30


# ─────────────────────────────────────────────────────────
# Isotonic Calibrator
# ─────────────────────────────────────────────────────────

class TestIsotonicCalibrator:

    def test_identity_before_fit(self):
        cal = IsotonicCalibrator("test_iso")
        for p in [0.1, 0.5, 0.9]:
            assert cal.calibrate(p) == p

    def test_state_not_ready_before_fit(self):
        cal = IsotonicCalibrator("test_iso_state")
        assert cal.state.isReady is False

    def test_fit_requires_min_samples(self):
        cal = IsotonicCalibrator("test_iso_min")
        for i in range(10):  # below MIN_FIT_SAMPLES=30
            cal.record(0.5, 1)
        result = cal.fit()
        assert result is False

    def test_fit_succeeds(self):
        cal = IsotonicCalibrator("test_iso_fit")
        for _ in range(40):
            cal.record(0.8, 1)
            cal.record(0.2, 0)
        result = cal.fit()
        assert result is True

    def test_calibrated_values_in_0_1(self):
        cal = IsotonicCalibrator("test_iso_range")
        for _ in range(40):
            cal.record(0.8, 1)
            cal.record(0.2, 0)
        cal.fit()
        for raw in [0.1, 0.5, 0.9]:
            c = cal.calibrate(raw)
            assert 0.0 <= c <= 1.0, f"Isotonic calibrated prob {c} out of range"

    def test_isotonic_monotonic(self):
        """Isotonic regression output must be non-decreasing."""
        cal = IsotonicCalibrator("test_iso_mono")
        # Provide a noisy but generally increasing signal
        import random
        random.seed(99)
        for _ in range(50):
            p = random.uniform(0.1, 0.9)
            label = 1 if p > 0.5 else 0
            cal.record(p, label)
        cal.fit()
        test_points = [0.1, 0.3, 0.5, 0.7, 0.9]
        calibrated = [cal.calibrate(p) for p in test_points]
        for i in range(len(calibrated) - 1):
            assert calibrated[i] <= calibrated[i + 1] + 1e-6, \
                f"Isotonic non-monotonic: {calibrated}"


# ─────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────

class TestCalibratorRegistry:

    def test_get_calibrator_creates_platt_by_default(self):
        cal = get_calibrator("reg_test_platt")
        assert isinstance(cal, PlattCalibrator)

    def test_get_calibrator_isotonic(self):
        cal = get_calibrator("reg_test_iso", method="isotonic")
        assert isinstance(cal, IsotonicCalibrator)

    def test_get_calibrator_idempotent(self):
        """Same name returns same instance."""
        c1 = get_calibrator("idempotent_test")
        c2 = get_calibrator("idempotent_test")
        assert c1 is c2

    def test_list_calibrators_returns_states(self):
        get_calibrator("list_test_a")
        get_calibrator("list_test_b")
        states = list_calibrators()
        assert isinstance(states, list)
        names = [s.method for s in states]
        assert "platt" in names

    def test_list_calibrators_contains_state_fields(self):
        get_calibrator("field_test")
        states = list_calibrators()
        assert len(states) > 0
        s = states[0]
        assert hasattr(s, "method")
        assert hasattr(s, "nFit")
        assert hasattr(s, "isReady")
        assert hasattr(s, "temperature")
        assert hasattr(s, "bias")
