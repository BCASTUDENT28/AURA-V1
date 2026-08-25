"""
backend/tests/test_realtime_gateway.py

Tests for WebSocket Gateway & Topic Filtering.
Verifies:
- Subscription management per client
- Topic matching and event delivery
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.app.realtime.event_bus import RealtimeEvent
from backend.app.realtime.gateway import WebSocketClient, WebSocketGateway


@pytest.mark.asyncio
async def test_websocket_client_topic_filtering():
    """Client only receives events matching its subscribed patterns."""
    mock_ws = AsyncMock()
    client = WebSocketClient("client-1", mock_ws)
    client.subscriptions.add("quotes:NIFTY")
    client.subscriptions.add("risk:*")

    # Match 1: quotes:NIFTY -> matches
    assert client.is_subscribed("quotes:NIFTY") is True
    # Non-match: quotes:RELIANCE -> does not match
    assert client.is_subscribed("quotes:RELIANCE") is False
    # Match 2: risk:alerts -> matches
    assert client.is_subscribed("risk:alerts") is True

    await client.send_event(RealtimeEvent(topic="quotes:NIFTY", payload={"ltp": 24000.0}))
    mock_ws.send_text.assert_called_once()
    sent_json = json.loads(mock_ws.send_text.call_args[0][0])
    assert sent_json["topic"] == "quotes:NIFTY"
    assert sent_json["payload"]["ltp"] == 24000.0


def test_gateway_subscription_lifecycle():
    """Gateway accurately manages client subscribe and unsubscribe."""
    gateway = WebSocketGateway()
    mock_ws = AsyncMock()
    client = WebSocketClient("c-100", mock_ws)
    gateway._clients["c-100"] = client

    gateway.subscribe("c-100", ["bars:BANKNIFTY:5m"])
    assert "bars:BANKNIFTY:5m" in client.subscriptions

    gateway.unsubscribe("c-100", ["bars:BANKNIFTY:5m"])
    assert "bars:BANKNIFTY:5m" not in client.subscriptions

    gateway.disconnect("c-100")
    assert "c-100" not in gateway._clients
