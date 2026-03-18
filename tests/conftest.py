"""Shared fixtures for Doppelchatter tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from doppelchatter.config import AppConfig, EngineConfig, LLMConfig, ServerConfig, TurnDelayConfig
from doppelchatter.models import (
    Message,
    MessageType,
    Session,
    TwinProfile,
)


@pytest.fixture
def shannon() -> TwinProfile:
    return TwinProfile(
        name="Shannon",
        system_prompt="You are Shannon. Be brief.",
        display_name="Shannon",
        avatar="🌙",
        color="#C084FC",
        description="Writer. Dreamer. Menace.",
    )


@pytest.fixture
def antreas() -> TwinProfile:
    return TwinProfile(
        name="Antreas",
        system_prompt="You are Antreas. Be brief.",
        display_name="Antreas",
        avatar="🔬",
        color="#F59E0B",
        description="Researcher. Builder.",
    )


@pytest.fixture
def session(shannon: TwinProfile, antreas: TwinProfile) -> Session:
    s = Session()
    s.twin_a = shannon
    s.twin_b = antreas
    return s


@pytest.fixture
def conversation() -> list[Message]:
    """A short conversation history for testing."""
    return [
        Message(
            type=MessageType.TWIN,
            content="hey x",
            sender="Shannon",
            twin_role="twin_a",
            turn_number=1,
        ),
        Message(
            type=MessageType.TWIN,
            content="hey.",
            sender="Antreas",
            twin_role="twin_b",
            turn_number=2,
        ),
        Message(
            type=MessageType.TWIN,
            content="can't sleep lol",
            sender="Shannon",
            twin_role="twin_a",
            turn_number=3,
        ),
        Message(
            type=MessageType.TWIN,
            content="same. working on a paper.",
            sender="Antreas",
            twin_role="twin_b",
            turn_number=4,
        ),
    ]


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(
        server=ServerConfig(host="127.0.0.1", port=8420),
        llm=LLMConfig(api_key="test-key", default_model="test/model"),
        engine=EngineConfig(
            turn_delay=TurnDelayConfig(mode="fixed", min_seconds=0.0, max_seconds=0.0),
            first_speaker="twin_a",
            max_turns=0,
            max_context_messages=50,
        ),
        sessions_dir="/tmp/doppelchatter-test-sessions",
    )


@pytest.fixture
def tmp_sessions(tmp_path: Path) -> Path:
    """Temporary sessions directory."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    return sessions


class MockLLMClient:
    """Deterministic LLM for tests. Returns canned responses per twin."""

    def __init__(self, responses: dict[str, list[str]] | None = None) -> None:
        self.responses = responses or {
            "Shannon": ["hey x", "lol yeah", "that's so funny 🤣"],
            "Antreas": ["hey.", "been thinking.", "yeah."],
        }
        self.call_count: dict[str, int] = {}
        self.last_context: list[dict[str, str]] | None = None

    async def stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.85,
        max_tokens: int = 512,
        fallback_chain: list[str] | None = None,
    ) -> AsyncIterator[str]:
        self.last_context = messages
        system = messages[0]["content"] if messages else ""
        for name, resps in self.responses.items():
            if name in system:
                idx = self.call_count.get(name, 0)
                self.call_count[name] = idx + 1
                text = resps[idx % len(resps)]
                for word in text.split():
                    yield word + " "
                return
        yield "..."

    async def close(self) -> None:
        pass


@pytest.fixture
def mock_llm() -> MockLLMClient:
    return MockLLMClient()
