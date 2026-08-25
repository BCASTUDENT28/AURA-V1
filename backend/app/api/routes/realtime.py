"""
backend/app/api/routes/realtime.py

FastAPI routes & WebSocket endpoint for Phase 6 Real-Time Engine:
- WebSocket /ws/stream
- POST /api/realtime/tick
- GET  /api/realtime/status
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.realtime.gateway import get_websocket_gateway
from backend.app.realtime.tick_ingest import TickPacket, get_tick_engine

router = APIRouter(tags=["Real-Time Streaming & Tick Gateway"])


@router.websocket("/ws/stream")
async def websocket_stream_endpoint(websocket: WebSocket):
    """
    Real-time streaming WebSocket endpoint for AURA AI:
    - Automatically subscribes client to quotes, decisions, risk alerts, and paper fills.
    - Supports client commands:
        `{"action": "subscribe", "topics": ["quotes:NIFTY"]}`
        `{"action": "unsubscribe", "topics": ["quotes:NIFTY"]}`
        `{"action": "ping"}`
    """
    gateway = get_websocket_gateway()
    client_id = f"client-{uuid.uuid4().hex[:8]}"
    client = await gateway.connect(client_id, websocket)

    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                data = json.loads(raw_msg)
                action = data.get("action")
                if action == "subscribe":
                    topics = data.get("topics", [])
                    gateway.subscribe(client_id, topics)
                    await websocket.send_text(json.dumps({
                        "type": "ACK",
                        "subscribed": list(client.subscriptions),
                    }))
                elif action == "unsubscribe":
                    topics = data.get("topics", [])
                    gateway.unsubscribe(client_id, topics)
                    await websocket.send_text(json.dumps({
                        "type": "ACK",
                        "subscribed": list(client.subscriptions),
                    }))
                elif action == "ping":
                    await websocket.send_text(json.dumps({"type": "PONG"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        gateway.disconnect(client_id)
    except Exception:
        gateway.disconnect(client_id)


@router.post("/api/realtime/tick")
async def ingest_market_tick(tick: TickPacket):
    """
    Ingest a live market tick:
    - Filters outlier spikes (>10% sudden jump).
    - Aggregates rolling 1-minute and 5-minute OHLCV candles dynamically.
    - Emits quote event to all subscribed WebSocket clients.
    """
    engine = get_tick_engine()
    res = await engine.ingest_tick(tick)
    return res


@router.get("/api/realtime/status")
def get_realtime_status():
    """Retrieve gateway status, active WebSocket client count, and tick processing throughput."""
    gateway = get_websocket_gateway()
    engine = get_tick_engine()

    return {
        "status": "RUNNING",
        "gateway": gateway.get_stats(),
        "ingestion": engine.get_metrics(),
    }
