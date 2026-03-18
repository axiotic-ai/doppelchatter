"""Tests for JSONL persistence and transcript export."""

from __future__ import annotations

import json
from pathlib import Path

from doppelchatter.models import Message, MessageType, Session, TwinProfile
from doppelchatter.storage import (
    SessionStore,
    check_unclean_shutdown,
    export_html,
    export_json,
    export_markdown,
)


class TestSessionStore:
    def test_save_and_load_session(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path / "sessions")
        session = Session(id="test123")
        session.twin_a = TwinProfile(name="A", system_prompt="Be A.")
        session.twin_b = TwinProfile(name="B", system_prompt="Be B.")
        store.save_session(session)

        loaded = store.load_session("test123")
        assert loaded is not None
        assert loaded["id"] == "test123"
        assert loaded["state"] == "idle"

    def test_append_and_load_messages(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path / "sessions")
        session = Session(id="msg123")
        store.save_session(session)

        msg = Message(type=MessageType.TWIN, content="hello", sender="Test")
        store.append_message("msg123", msg)

        loaded = store.load_session("msg123")
        assert loaded is not None
        assert len(loaded["messages"]) == 1
        assert loaded["messages"][0]["content"] == "hello"

    def test_append_multiple_messages(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path / "sessions")
        session = Session(id="multi")
        store.save_session(session)

        for i in range(5):
            msg = Message(type=MessageType.TWIN, content=f"msg{i}", sender="Test")
            store.append_message("multi", msg)

        loaded = store.load_session("multi")
        assert loaded is not None
        assert len(loaded["messages"]) == 5

    def test_load_nonexistent_session(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path / "sessions")
        assert store.load_session("nonexistent") is None

    def test_list_sessions(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path / "sessions")
        for i in range(3):
            session = Session(id=f"sess{i}")
            store.save_session(session)

        sessions = store.list_sessions()
        assert len(sessions) == 3

    def test_list_sessions_empty(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path / "sessions")
        assert store.list_sessions() == []

    def test_creates_directories(self, tmp_path: Path) -> None:
        store = SessionStore(tmp_path / "deep" / "nested" / "sessions")
        session = Session(id="deep1")
        store.save_session(session)
        assert (tmp_path / "deep" / "nested" / "sessions" / "deep1" / "session.json").exists()


class TestUncleanShutdown:
    def test_marks_running_as_stopped(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "crashed"
        session_dir.mkdir()
        (session_dir / "session.json").write_text(
            json.dumps({"id": "crashed", "state": "running"})
        )
        check_unclean_shutdown(tmp_path)
        data = json.loads((session_dir / "session.json").read_text())
        assert data["state"] == "stopped"
        assert data["metadata"]["unclean_shutdown"] is True

    def test_marks_paused_as_stopped(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "paused"
        session_dir.mkdir()
        (session_dir / "session.json").write_text(
            json.dumps({"id": "paused", "state": "paused"})
        )
        check_unclean_shutdown(tmp_path)
        data = json.loads((session_dir / "session.json").read_text())
        assert data["state"] == "stopped"

    def test_leaves_stopped_alone(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "done"
        session_dir.mkdir()
        (session_dir / "session.json").write_text(
            json.dumps({"id": "done", "state": "stopped"})
        )
        check_unclean_shutdown(tmp_path)
        data = json.loads((session_dir / "session.json").read_text())
        assert data["state"] == "stopped"
        assert "metadata" not in data or "unclean_shutdown" not in data.get("metadata", {})

    def test_leaves_idle_alone(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "idle"
        session_dir.mkdir()
        (session_dir / "session.json").write_text(
            json.dumps({"id": "idle", "state": "idle"})
        )
        check_unclean_shutdown(tmp_path)
        data = json.loads((session_dir / "session.json").read_text())
        assert data["state"] == "idle"

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        check_unclean_shutdown(tmp_path / "nope")  # Should not raise


class TestExportJson:
    def test_valid_json(self) -> None:
        data = {"id": "test", "messages": [], "turn_count": 5}
        result = export_json(data)
        parsed = json.loads(result)
        assert parsed["id"] == "test"
        assert parsed["turn_count"] == 5


class TestExportMarkdown:
    def test_basic_export(self) -> None:
        data = {
            "id": "test",
            "created_at": "2026-03-17T00:00:00",
            "turn_count": 2,
            "twin_a": {"display_name": "Shannon", "color": "#C084FC"},
            "twin_b": {"display_name": "Antreas", "color": "#F59E0B"},
            "messages": [
                {"type": "twin", "sender": "Shannon", "content": "hey x", "twin_role": "twin_a"},
                {"type": "twin", "sender": "Antreas", "content": "hey.", "twin_role": "twin_b"},
            ],
        }
        md = export_markdown(data)
        assert "# Shannon × Antreas" in md
        assert "**Shannon**" in md
        assert "hey x" in md
        assert "**Antreas**" in md
        assert "Exported from Doppelchatter" in md

    def test_thought_export(self) -> None:
        data = {
            "id": "test",
            "created_at": "2026-03-17",
            "turn_count": 1,
            "twin_a": {"display_name": "Shannon"},
            "twin_b": {"display_name": "Antreas"},
            "messages": [
                {
                    "type": "thought",
                    "sender": "Director",
                    "content": "Be honest",
                    "metadata": {"target_name": "Shannon"},
                },
            ],
        }
        md = export_markdown(data)
        assert "💭" in md
        assert "Shannon" in md
        assert "Be honest" in md

    def test_third_agent_export(self) -> None:
        data = {
            "id": "test",
            "created_at": "2026-03-17",
            "turn_count": 1,
            "twin_a": {"display_name": "A"},
            "twin_b": {"display_name": "B"},
            "messages": [
                {"type": "third_agent", "sender": "Mike", "content": "Hey!"},
            ],
        }
        md = export_markdown(data)
        assert "🎭 Mike" in md


class TestExportHtml:
    def test_produces_valid_html(self) -> None:
        data = {
            "id": "test",
            "turn_count": 1,
            "twin_a": {"display_name": "Shannon", "color": "#C084FC"},
            "twin_b": {"display_name": "Antreas", "color": "#F59E0B"},
            "messages": [
                {"type": "twin", "sender": "Shannon", "content": "hello", "twin_role": "twin_a"},
            ],
        }
        html = export_html(data)
        assert "<!DOCTYPE html>" in html
        assert "Shannon" in html
        assert "hello" in html
        assert "— fin —" in html

    def test_html_escapes_content(self) -> None:
        data = {
            "id": "test",
            "turn_count": 1,
            "twin_a": {"display_name": "A"},
            "twin_b": {"display_name": "B"},
            "messages": [
                {
                    "type": "twin", "sender": "A",
                    "content": "<script>alert('xss')</script>",
                    "twin_role": "twin_a",
                },
            ],
        }
        html = export_html(data)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
