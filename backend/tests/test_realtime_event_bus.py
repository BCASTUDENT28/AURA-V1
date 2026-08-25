"""
backend/tests/test_realtime_event_bus.py

Tests for Asynchronous Pub/Sub Event Bus.
Verifies:
- Wildcard topic pattern matching ('quotes:*', 'decisions:*')
- Multi-subscriber dispatch without dropped events
- Error isolation when one subscriber raises an exception
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.realtime.event_bus import EventBus, RealtimeEvent


@pytest.mark.asyncio
async def test_event_bus_pattern_subscription():
    """Wildcard subscription receives all matching topic publications."""
    bus = EventBus()
    received: list[RealtimeEvent] = []

    async def quote_handler(event: RealtimeEvent):
        received.append(event)

    bus.subscribe("quotes:*", quote_handler)

    await bus.publish("quotes:NIFTY", {"ltp": 24000.0})
    await bus.publish("quotes:RELIANCE", {"ltp": 2800.0})
    await bus.publish("risk:alerts", {"rule": "EXPOSURE"})  # Should NOT match

    assert len(received) == 2
    assert received[0].topic == "quotes:NIFTY"
    assert received[1].topic == "quotes:RELIANCE"


@pytest.mark.asyncio
async def test_event_bus_error_isolation():
    """Failing subscriber does not block other subscribers."""
    bus = EventBus()
    handled_second: list[str] = []

    async def broken_handler(event: RealtimeEvent):
        raise RuntimeError("Simulated crash in handler")

    async def good_handler(event: RealtimeEvent):
        handled_second.append(event.topic)

    bus.subscribe("decisions:*", broken_handler)
    bus.subscribe("decisions:*", good_handler)

    await bus.publish("decisions:TCS", {"action": "BUY"})

    assert len(handled_second) == 1
    assert handled_second[0] == "decisions:TCS"
