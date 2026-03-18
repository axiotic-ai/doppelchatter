"""Data models, state machine, and error hierarchy for Doppelchatter."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# ─── State Machine ────────────────────────────────────────────────────────────


class SessionState(StrEnum):
    """Five states. Clean, sufficient, recoverable."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


VALID_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.IDLE: {SessionState.RUNNING},
    SessionState.RUNNING: {SessionState.PAUSED, SessionState.ERROR, SessionState.STOPPED},
    SessionState.PAUSED: {SessionState.RUNNING, SessionState.STOPPED},
    SessionState.ERROR: {SessionState.RUNNING, SessionState.PAUSED, SessionState.STOPPED},
    SessionState.STOPPED: set(),
}


def validate_transition(current: SessionState, target: SessionState) -> bool:
    """Validate state transition. Raises InvalidTransitionError on invalid."""
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(
            f"Cannot transition from {current} to {target}. "
            f"Valid targets: {VALID_TRANSITIONS.get(current, set())}"
        )
    return True


class ActivePhase(StrEnum):
    """Substates within RUNNING — tracked as a field, not FSM states."""

    THINKING = "thinking"
    GENERATING = "generating"
    TRANSITIONING = "transitioning"


# ─── Message Model ────────────────────────────────────────────────────────────


class MessageType(StrEnum):
    TWIN = "twin"
    THIRD_AGENT = "third_agent"
    THOUGHT = "thought"
    SYSTEM = "system"


@dataclass
class Message:
    type: MessageType
    content: str
    sender: str = ""
    twin_role: str = ""
    turn_number: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "sender": self.sender,
            "twin_role": self.twin_role,
            "turn_number": self.turn_number,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


# ─── Twin Profile ─────────────────────────────────────────────────────────────


class ModelConfig(BaseModel):
    """Per-twin LLM model overrides. None = use global default."""

    name: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    fallback_chain: list[str] = Field(default_factory=list)


class BehaviorConfig(BaseModel):
    """Per-twin behavior settings."""

    multi_message: bool = False
    max_messages_per_turn: int = 3
    max_message_length: int = 280


class TwinProfile(BaseModel):
    """A twin's complete personality definition. Loaded from YAML."""

    model_config = {"extra": "ignore"}

    # Required
    name: str
    system_prompt: str

    # Display
    display_name: str | None = None
    avatar: str = "👤"
    color: str = "#6B7280"
    description: str = ""

    # LLM config
    model: ModelConfig = Field(default_factory=ModelConfig)

    # Behavior
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)

    # Context enrichment
    background: str = ""
    memories: list[str] = Field(default_factory=list)
    current_mood: str = ""

    # Metadata
    tags: list[str] = Field(default_factory=list)
    version: int = 1

    @property
    def effective_display_name(self) -> str:
        return self.display_name or self.name

    def to_summary(self) -> dict[str, str]:
        return {
            "name": self.name,
            "display_name": self.effective_display_name,
            "avatar": self.avatar,
            "color": self.color,
            "description": self.description,
        }


# ─── Session Model ────────────────────────────────────────────────────────────


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: SessionState = SessionState.IDLE
    active_phase: ActivePhase | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    twin_a: TwinProfile | None = None
    twin_b: TwinProfile | None = None

    turn_count: int = 0
    current_speaker: str = "twin_a"
    messages: list[Message] = field(default_factory=list)

    pending_thoughts: list[dict[str, str]] = field(default_factory=list)
    pending_agents: list[dict[str, str]] = field(default_factory=list)

    scenario_name: str = ""
    scenario_text: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "state": self.state.value,
            "active_phase": self.active_phase.value if self.active_phase else None,
            "created_at": self.created_at.isoformat(),
            "turn_count": self.turn_count,
            "current_speaker": self.current_speaker,
            "message_count": len(self.messages),
            "twin_a": self.twin_a.to_summary() if self.twin_a else None,
            "twin_b": self.twin_b.to_summary() if self.twin_b else None,
            "scenario_name": self.scenario_name,
            "pending_thoughts": len(self.pending_thoughts),
        }


# ─── Error Hierarchy ──────────────────────────────────────────────────────────


class DoppelError(Exception):
    """Base error for all Doppelchatter errors."""

    code: str = "UNKNOWN_ERROR"
    recoverable: bool = True


class ConfigurationError(DoppelError):
    code = "CONFIG_ERROR"
    recoverable = False


class ProfileNotFoundError(DoppelError):
    code = "PROFILE_NOT_FOUND"


class InvalidTransitionError(DoppelError):
    code = "INVALID_TRANSITION"


class LLMError(DoppelError):
    code = "LLM_ERROR"


class RateLimitError(LLMError):
    code = "RATE_LIMITED"

    def __init__(self, retry_after: float = 5.0):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after}s")


class ModelUnavailableError(LLMError):
    code = "MODEL_UNAVAILABLE"


class GenerationTimeoutError(LLMError):
    code = "GENERATION_TIMEOUT"


class APIKeyError(LLMError):
    code = "API_KEY_ERROR"
    recoverable = False
