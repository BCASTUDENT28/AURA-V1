"""
backend/tests/test_determinism.py

Determinism guarantee tests.
compute_decision() called twice with identical seed/inputs must produce
structurally identical canonical JSON (sorted keys, floats within 1e-6).
"""

from __future__ import annotations

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.data.simulator import bars_of, seed_quotes, PAPER_OPEN
from backend.app.engines.decision.decision import compute_decision

SYMBOLS = ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK"]
FLOAT_TOL = 1e-6


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def _run(symbol: str) -> dict:
    bars = bars_of(symbol, "1D")
    quotes = seed_quotes(PAPER_OPEN)
    d = compute_decision(symbol, bars, quotes[symbol], learnings=[])
    return json.loads(d.model_dump_json())


def _deep_float_compare(a, b, path: str = "", tol: float = FLOAT_TOL) -> list[str]:
    errors = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            if k not in a:
                errors.append(f"{path}.{k}: key missing in first run")
            elif k not in b:
                errors.append(f"{path}.{k}: key missing in second run")
            else:
                errors.extend(_deep_float_compare(a[k], b[k], f"{path}.{k}", tol))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            errors.append(f"{path}: list length {len(a)} vs {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                errors.extend(_deep_float_compare(x, y, f"{path}[{i}]", tol))
    elif isinstance(a, float) and isinstance(b, float):
        if not (math.isnan(a) and math.isnan(b)):
            if abs(a - b) > tol:
                errors.append(f"{path}: float {a:.10f} vs {b:.10f} (diff {abs(a-b):.2e})")
    else:
        if a != b:
            errors.append(f"{path}: {a!r} != {b!r}")
    return errors


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_determinism_same_output(symbol: str):
    """compute_decision() must return identical output on repeated calls."""
    a = _run(symbol)
    b = _run(symbol)
    errors = _deep_float_compare(a, b)
    assert not errors, (
        f"Non-deterministic output for {symbol}:\n" + "\n".join(errors)
    )


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_determinism_canonical_json_identical(symbol: str):
    """Canonical JSON (sorted keys) must be byte-for-byte identical."""
    a = canonical_json(_run(symbol))
    b = canonical_json(_run(symbol))
    assert a == b, f"Canonical JSON differs for {symbol} between runs"


def test_determinism_across_symbols_independent():
    """
    Running decisions for multiple symbols in sequence must not affect each other.
    Each symbol's output should be the same whether run alone or together.
    """
    # Run each symbol independently
    independent = {sym: _run(sym) for sym in SYMBOLS}

    # Run all symbols again — order matters for any stateful side-effects
    together_1 = {sym: _run(sym) for sym in SYMBOLS}
    together_2 = {sym: _run(sym) for sym in reversed(SYMBOLS)}

    for sym in SYMBOLS:
        errors_1 = _deep_float_compare(independent[sym], together_1[sym])
        assert not errors_1, f"{sym}: mismatch independent vs forward order\n" + "\n".join(errors_1)

        errors_2 = _deep_float_compare(independent[sym], together_2[sym])
        assert not errors_2, f"{sym}: mismatch independent vs reverse order\n" + "\n".join(errors_2)


@pytest.mark.parametrize("symbol", ["NIFTY", "BANKNIFTY"])
def test_simulator_bars_deterministic(symbol: str):
    """The simulator must return identical bars on repeated calls."""
    bars_a = bars_of(symbol, "1D")
    bars_b = bars_of(symbol, "1D")
    assert len(bars_a) == len(bars_b)
    for i, (a, b) in enumerate(zip(bars_a, bars_b)):
        assert a.model_dump() == b.model_dump(), f"Bar {i} mismatch for {symbol}"


@pytest.mark.parametrize("symbol", ["NIFTY", "BANKNIFTY"])
def test_simulator_quotes_deterministic(symbol: str):
    """seed_quotes() must return identical quotes on repeated calls."""
    qa = seed_quotes(PAPER_OPEN)
    qb = seed_quotes(PAPER_OPEN)
    a = qa[symbol].model_dump()
    b = qb[symbol].model_dump()
    assert a == b, f"Quote mismatch for {symbol}"
