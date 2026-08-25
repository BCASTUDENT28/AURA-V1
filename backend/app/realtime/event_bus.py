"""
backend/app/realtime/event_bus.py

Asynchronous In-Process Event Bus for AURA AI Real-Time Engine.
Topics:
- `quotes:{symbol}` -> Live tick & quote broadcasts
- `bars:{symbol}:{timeframe}` -> Completed candle emissions
- `decisions:{symbol}` -> Real-time AI decisions
- `risk:alerts` -> Risk threshold warnings & breaches
- `paper:fills` -> Server-side paper trading executions
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
from typing import Any, Callable, Coroutine, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RealtimeEvent(BaseModel):
    topic: str
    payload: Any
    ts: int = 0


EventHandler = Callable[[RealtimeEvent], Coroutine[Any, Any, None]]


class EventBus:
    """Non-blocking asynchronous publish/subscribe event bus."""

    def __init__(self):
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._history: list[RealtimeEvent] = []

    def subscribe(self, topic_pattern: str, handler: EventHandler) -> None:
        """Subscribe an async handler to a topic pattern (e.g. 'quotes:*' or 'risk:alerts')."""
        if topic_pattern not in self._subscribers:
            self._subscribers[topic_pattern] = []
        if handler not in self._subscribers[topic_pattern]:
            self._subscribers[topic_pattern].append(handler)

    def unsubscribe(self, topic_pattern: str, handler: EventHandler) -> None:
        """Unsubscribe an async handler."""
        if topic_pattern in self._subscribers and handler in self._subscribers[topic_pattern]:
            self._subscribers[topic_pattern].remove(handler)

    async def publish(self, topic: str, payload: Any) -> None:
        """Publish an event across all matching topic subscribers."""
        event = RealtimeEvent(
            topic=topic,
            payload=payload,
            ts=int(time.time() * 1000),
        )
        self._history.append(event)
        if len(self._history) > 1000:
            self._history.pop(0)

        tasks = []
        for pattern, handlers in self._subscribers.items():
            if fnmatch.fnmatch(topic, pattern):
                for handler in handlers:
                    tasks.append(self._safe_dispatch(handler, event))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_dispatch(self, handler: EventHandler, event: RealtimeEvent) -> None:
        try:
            await handler(event)
        except Exception as exc:
            logger.error("Error in event handler %s for topic %s: %s", handler, event.topic, exc)

    def clear(self) -> None:
        """Clear all subscribers and history."""
        self._subscribers.clear()
        self._history.clear()


# Global singleton event bus
_event_bus = EventBus()


def get_event_bus() -> EventBus:
    return _event_bus
