"""WebSocket manager — connection tracking, broadcasting, and event buffering."""

from __future__ import annotations

import json
import logging
from collections import deque

from fastapi import WebSocket

logger = logging.getLogger(__name__)

MAX_EVENT_BUFFER = 500


class WebSocketManager:
    """Manages WebSocket connections, broadcasts, and event buffering for resync."""

    def __init__(self) -> None:
        self._clients: list[WebSocket] = []
        self._sequence: int = 0
        self._event_buffer: deque[dict[str, object]] = deque(maxlen=MAX_EVENT_BUFFER)

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.append(ws)
        logger.info(f"WebSocket connected. Total clients: {len(self._clients)}")

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._clients:
            self._clients.remove(ws)
            logger.info(f"WebSocket disconnected. Total clients: {len(self._clients)}")

    async def broadcast(self, event_type: str, data: dict[str, object] | None = None) -> None:
        """Broadcast an event to all connected clients with sequence number."""
        self._sequence += 1
        payload: dict[str, object] = {
            "type": event_type,
            "sequence": self._sequence,
            **(data or {}),
        }
        self._event_buffer.append(payload)

        message = json.dumps(payload, default=str)
        disconnected: list[WebSocket] = []
        for ws in self._clients:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    async def send(
        self, ws: WebSocket, event_type: str, data: dict[str, object] | None = None
    ) -> None:
        """Send to a single client (no sequence, not buffered)."""
        payload: dict[str, object] = {"type": event_type, **(data or {})}
        await ws.send_text(json.dumps(payload, default=str))

    async def resync(self, ws: WebSocket, last_sequence: int) -> None:
        """Send missed events to a reconnecting client."""
        missed = [e for e in self._event_buffer if e.get("sequence", 0) > last_sequence]  # type: ignore[operator]
        for event in missed:
            try:
                await ws.send_text(json.dumps(event, default=str))
            except Exception:
                break
