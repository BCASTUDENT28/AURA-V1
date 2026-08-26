"""
backend/app/ml/calibration.py

Probability Calibration for AURA AI (Phase 7).

Implements Platt Scaling (sigmoid calibration) and
Isotonic Regression (piecewise constant calibration).

Usage:
  - After a model produces raw probability estimates, apply calibration
    to get better-aligned P(outcome | score) values.
  - Calibrator uses historical (score, outcome) pairs to fit parameters.
  - Deployed online: calibrate raw probs before surfacing to API consumers.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel


CalibrationMethod = Literal["platt", "isotonic", "identity"]


class CalibrationState(BaseModel):
    method: CalibrationMethod
    nFit: int
    temperature: float
    bias: float
    isReady: bool


class PlattCalibrator:
    """
    Platt Scaling: p_cal = sigmoid(A * logit(p_raw) + B)
    A (temperature) and B (bias) fitted via gradient descent on (score, label) pairs.
    """

    MIN_FIT_SAMPLES = 50
    LEARNING_RATE = 0.05
    PRIOR_A = 1.0   # start near identity transform
    PRIOR_B = 0.0

    def __init__(self, name: str) -> None:
        self.name = name
        self._A = self.PRIOR_A
        self._B = self.PRIOR_B
        self._samples: list[tuple[float, int]] = []  # (raw_prob, label 0/1)

    def _sigmoid(self, x: float) -> float:
        return 1.0 / (1.0 + math.exp(-x))

    def _logit(self, p: float) -> float:
        p = max(1e-7, min(1 - 1e-7, p))
        return math.log(p / (1 - p))

    def record(self, raw_prob: float, label: int) -> None:
        """Record a (prediction, outcome) pair for online calibration."""
        self._samples.append((raw_prob, label))

    def fit(self) -> bool:
        """Fit Platt parameters using gradient descent on recorded pairs."""
        if len(self._samples) < self.MIN_FIT_SAMPLES:
            return False

        A, B = self._A, self._B
        for _ in range(200):  # mini-batch gradient descent
            dA = dB = 0.0
            for p_raw, y in self._samples:
                logit_p = self._logit(p_raw)
                p_cal = self._sigmoid(A * logit_p + B)
                err = p_cal - y
                dA += err * logit_p
                dB += err
            n = len(self._samples)
            A -= self.LEARNING_RATE * dA / n
            B -= self.LEARNING_RATE * dB / n

        self._A = A
        self._B = B
        return True

    def calibrate(self, raw_prob: float) -> float:
        """Apply fitted Platt calibration to a raw probability."""
        if len(self._samples) < self.MIN_FIT_SAMPLES:
            return raw_prob  # Identity fallback
        logit_p = self._logit(raw_prob)
        return round(self._sigmoid(self._A * logit_p + self._B), 6)

    @property
    def state(self) -> CalibrationState:
        return CalibrationState(
            method="platt",
            nFit=len(self._samples),
            temperature=round(self._A, 4),
            bias=round(self._B, 4),
            isReady=len(self._samples) >= self.MIN_FIT_SAMPLES,
        )


class IsotonicCalibrator:
    """
    Isotonic Regression calibration via Pool Adjacent Violators (PAV) algorithm.
    Non-parametric; better when P(y|score) is non-monotonic.
    """

    MIN_FIT_SAMPLES = 30

    def __init__(self, name: str) -> None:
        self.name = name
        self._samples: list[tuple[float, int]] = []
        self._thresholds: list[float] = []
        self._values: list[float] = []

    def record(self, raw_prob: float, label: int) -> None:
        self._samples.append((raw_prob, label))

    def fit(self) -> bool:
        if len(self._samples) < self.MIN_FIT_SAMPLES:
            return False

        # Sort by raw_prob
        pairs = sorted(self._samples, key=lambda x: x[0])
        probs = [p[0] for p in pairs]
        labels = [p[1] for p in pairs]

        # PAV algorithm
        blocks: list[list[tuple[float, int]]] = [[p] for p in zip(probs, labels)]
        changed = True
        while changed:
            changed = False
            new_blocks: list[list[tuple[float, int]]] = []
            i = 0
            while i < len(blocks):
                block = blocks[i]
                if i + 1 < len(blocks):
                    next_block = blocks[i + 1]
                    mean_curr = sum(b[1] for b in block) / len(block)
                    mean_next = sum(b[1] for b in next_block) / len(next_block)
                    if mean_curr > mean_next:  # Violation — merge
                        new_blocks.append(block + next_block)
                        i += 2
                        changed = True
                        continue
                new_blocks.append(block)
                i += 1
            blocks = new_blocks

        # Flatten to lookup table
        self._thresholds = []
        self._values = []
        for block in blocks:
            mean_prob = sum(b[0] for b in block) / len(block)
            mean_label = sum(b[1] for b in block) / len(block)
            self._thresholds.append(mean_prob)
            self._values.append(mean_label)
        return True

    def calibrate(self, raw_prob: float) -> float:
        if not self._thresholds:
            return raw_prob
        # Binary search for nearest threshold
        lo, hi = 0, len(self._thresholds) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self._thresholds[mid] < raw_prob:
                lo = mid + 1
            else:
                hi = mid
        return round(self._values[lo], 6)

    @property
    def state(self) -> CalibrationState:
        return CalibrationState(
            method="isotonic",
            nFit=len(self._samples),
            temperature=1.0,
            bias=0.0,
            isReady=len(self._samples) >= self.MIN_FIT_SAMPLES,
        )


# ─── Registry ────────────────────────────────────────────────────────────────

_CALIBRATORS: dict[str, PlattCalibrator | IsotonicCalibrator] = {}


def get_calibrator(
    name: str,
    method: CalibrationMethod = "platt",
) -> PlattCalibrator | IsotonicCalibrator:
    """Get or create a named calibrator."""
    if name not in _CALIBRATORS:
        if method == "isotonic":
            _CALIBRATORS[name] = IsotonicCalibrator(name)
        else:
            _CALIBRATORS[name] = PlattCalibrator(name)
    return _CALIBRATORS[name]


def list_calibrators() -> list[CalibrationState]:
    return [c.state for c in _CALIBRATORS.values()]
