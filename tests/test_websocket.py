"""Tests for WebSocket manager."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from doppelchatter.websocket import MAX_EVENT_BUFFER, WebSocketManager


def make_mock_ws() -> AsyncMock:
    """Create a mock WebSocket with send_text."""
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


class TestWebSocketManager:
    @pytest.fixture
    def manager(self) -> WebSocketManager:
        return WebSocketManager()

    @pytest.mark.asyncio
    async def test_connect(self, manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await manager.connect(ws)
        assert manager.client_count == 1
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self, manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await manager.connect(ws)
        manager.disconnect(ws)
        assert manager.client_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self, manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        manager.disconnect(ws)  # Should not raise
        assert manager.client_count == 0

    @pytest.mark.asyncio
    async def test_broadcast(self, manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await manager.connect(ws)
        await manager.broadcast("test_event", {"key": "value"})

        ws.send_text.assert_called_once()
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "test_event"
        assert sent["key"] == "value"
        assert sent["sequence"] == 1

    @pytest.mark.asyncio
    async def test_broadcast_sequence_increments(self, manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await manager.connect(ws)
        await manager.broadcast("e1")
        await manager.broadcast("e2")
        await manager.broadcast("e3")

        assert manager.sequence == 3

    @pytest.mark.asyncio
    async def test_broadcast_multiple_clients(self, manager: WebSocketManager) -> None:
        ws1 = make_mock_ws()
        ws2 = make_mock_ws()
        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.broadcast("event")

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_client(self, manager: WebSocketManager) -> None:
        ws1 = make_mock_ws()
        ws2 = make_mock_ws()
        ws2.send_text.side_effect = Exception("Connection closed")
        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.broadcast("event")

        assert manager.client_count == 1

    @pytest.mark.asyncio
    async def test_send_to_single(self, manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await manager.send(ws, "direct", {"msg": "hello"})
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "direct"
        assert sent["msg"] == "hello"
        assert "sequence" not in sent  # send() doesn't add sequence

    @pytest.mark.asyncio
    async def test_resync_sends_missed_events(self, manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await manager.connect(ws)

        # Broadcast 5 events
        for i in range(5):
            await manager.broadcast(f"event_{i}")

        # New client wants events after sequence 2
        ws2 = make_mock_ws()
        await manager.resync(ws2, 2)

        # Should receive events 3, 4, 5
        assert ws2.send_text.call_count == 3

    @pytest.mark.asyncio
    async def test_resync_all_events(self, manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await manager.connect(ws)
        await manager.broadcast("e1")
        await manager.broadcast("e2")

        ws2 = make_mock_ws()
        await manager.resync(ws2, 0)
        assert ws2.send_text.call_count == 2

    @pytest.mark.asyncio
    async def test_event_buffer_limit(self, manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await manager.connect(ws)
        for i in range(MAX_EVENT_BUFFER + 100):
            await manager.broadcast(f"e_{i}")

        # Buffer should cap at MAX_EVENT_BUFFER
        ws2 = make_mock_ws()
        await manager.resync(ws2, 0)
        assert ws2.send_text.call_count == MAX_EVENT_BUFFER

    @pytest.mark.asyncio
    async def test_broadcast_no_data(self, manager: WebSocketManager) -> None:
        ws = make_mock_ws()
        await manager.connect(ws)
        await manager.broadcast("ping")
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "ping"
        assert sent["sequence"] == 1
