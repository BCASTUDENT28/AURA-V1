"""
backend/app/realtime/gateway.py

WebSocket Gateway & Client Connection Manager for AURA AI.
Multiplexes real-time subscriptions per client:
- `quotes:{symbol}`
- `bars:{symbol}:{timeframe}`
- `decisions:{symbol}`
- `risk:alerts`
- `paper:fills`
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
from typing import Any, Optional
from fastapi import WebSocket

from backend.app.realtime.event_bus import RealtimeEvent, get_event_bus

logger = logging.getLogger(__name__)


class WebSocketClient:
    """Represents an active client WebSocket session."""

    def __init__(self, client_id: str, websocket: WebSocket):
        self.client_id = client_id
        self.websocket = websocket
        self.subscriptions: set[str] = set()

    def is_subscribed(self, topic: str) -> bool:
        for sub in self.subscriptions:
            if fnmatch.fnmatch(topic, sub):
                return True
        return False

    async def send_event(self, event: RealtimeEvent) -> None:
        try:
            await self.websocket.send_text(
                json.dumps({
                    "topic": event.topic,
                    "payload": event.payload,
                    "ts": event.ts,
                })
            )
        except Exception as exc:
            logger.debug("Failed to send to client %s: %s", self.client_id, exc)


class WebSocketGateway:
    """Manages connected WebSocket clients and delivers matching stream events."""

    def __init__(self):
        self._clients: dict[str, WebSocketClient] = {}
        self._is_hooked = False

    def hook_event_bus(self) -> None:
        """Attach gateway broadcaster to the global EventBus."""
        if not self._is_hooked:
            bus = get_event_bus()
            bus.subscribe("*", self._on_bus_event)
            self._is_hooked = True

    async def connect(self, client_id: str, websocket: WebSocket) -> WebSocketClient:
        await websocket.accept()
        client = WebSocketClient(client_id, websocket)
        # Default subscriptions for all clients
        client.subscriptions.add("quotes:*")
        client.subscriptions.add("decisions:*")
        client.subscriptions.add("risk:alerts")
        client.subscriptions.add("paper:fills")

        self._clients[client_id] = client
        self.hook_event_bus()
        return client

    def disconnect(self, client_id: str) -> None:
        if client_id in self._clients:
            del self._clients[client_id]

    def subscribe(self, client_id: str, topics: list[str]) -> None:
        client = self._clients.get(client_id)
        if client:
            for t in topics:
                client.subscriptions.add(t)

    def unsubscribe(self, client_id: str, topics: list[str]) -> None:
        client = self._clients.get(client_id)
        if client:
            for t in topics:
                client.subscriptions.discard(t)

    async def _on_bus_event(self, event: RealtimeEvent) -> None:
        tasks = []
        for client in self._clients.values():
            if client.is_subscribed(event.topic):
                tasks.append(client.send_event(event))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_stats(self) -> dict[str, Any]:
        return {
            "activeClients": len(self._clients),
            "clientIds": list(self._clients.keys()),
        }


# Global singleton gateway
_gateway = WebSocketGateway()


def get_websocket_gateway() -> WebSocketGateway:
    return _gateway
