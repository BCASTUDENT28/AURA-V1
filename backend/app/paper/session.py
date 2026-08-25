"""
backend/app/paper/session.py

Paper Session Manager for AURA AI.
Tracks session start, duration, status (open/archived), and initial starting capital.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional
from pydantic import BaseModel

from backend.app.schemas.types import STARTING_CASH


class PaperSessionInfo(BaseModel):
    id: str
    startedAt: int
    closedAt: Optional[int] = None
    startingCash: float = STARTING_CASH
    status: str = "open"               # "open" | "closed" | "archived"
    env: str = "PAPER"
    dataSource: str = "PERSISTENT_AND_SIMULATOR"


class PaperSessionManager:
    """Manages paper trading session lifecycle."""

    def __init__(self):
        self._current_session = PaperSessionInfo(
            id=f"session-paper-{uuid.uuid4().hex[:8]}",
            startedAt=int(time.time() * 1000),
        )
        self._archived_sessions: list[PaperSessionInfo] = []

    def get_current_session(self) -> PaperSessionInfo:
        return self._current_session

    def archive_and_new_session(self) -> PaperSessionInfo:
        now_ms = int(time.time() * 1000)
        self._current_session.status = "archived"
        self._current_session.closedAt = now_ms
        self._archived_sessions.append(self._current_session)

        self._current_session = PaperSessionInfo(
            id=f"session-paper-{uuid.uuid4().hex[:8]}",
            startedAt=now_ms,
        )
        return self._current_session

    def list_archived_sessions(self) -> list[PaperSessionInfo]:
        return self._archived_sessions


_session_manager = PaperSessionManager()


def get_paper_session_manager() -> PaperSessionManager:
    return _session_manager
