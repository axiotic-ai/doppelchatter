"""Tests for models — state machine, message, session, twin profile."""

from __future__ import annotations

import pytest

from doppelchatter.models import (
    VALID_TRANSITIONS,
    ActivePhase,
    InvalidTransitionError,
    Message,
    MessageType,
    Session,
    SessionState,
    TwinProfile,
    validate_transition,
)

# ─── State Machine ───────────────────────────────────────────────────────────


class TestStateMachine:
    def test_idle_to_running(self) -> None:
        assert validate_transition(SessionState.IDLE, SessionState.RUNNING)

    def test_running_to_paused(self) -> None:
        assert validate_transition(SessionState.RUNNING, SessionState.PAUSED)

    def test_running_to_error(self) -> None:
        assert validate_transition(SessionState.RUNNING, SessionState.ERROR)

    def test_running_to_stopped(self) -> None:
        assert validate_transition(SessionState.RUNNING, SessionState.STOPPED)

    def test_paused_to_running(self) -> None:
        assert validate_transition(SessionState.PAUSED, SessionState.RUNNING)

    def test_paused_to_stopped(self) -> None:
        assert validate_transition(SessionState.PAUSED, SessionState.STOPPED)

    def test_error_to_running(self) -> None:
        assert validate_transition(SessionState.ERROR, SessionState.RUNNING)

    def test_error_to_paused(self) -> None:
        assert validate_transition(SessionState.ERROR, SessionState.PAUSED)

    def test_error_to_stopped(self) -> None:
        assert validate_transition(SessionState.ERROR, SessionState.STOPPED)

    def test_stopped_is_terminal(self) -> None:
        assert VALID_TRANSITIONS[SessionState.STOPPED] == set()
        for state in SessionState:
            if state != SessionState.STOPPED:
                with pytest.raises(InvalidTransitionError):
                    validate_transition(SessionState.STOPPED, state)

    def test_no_self_transitions(self) -> None:
        for state in SessionState:
            assert state not in VALID_TRANSITIONS.get(state, set())

    def test_idle_cannot_pause(self) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_transition(SessionState.IDLE, SessionState.PAUSED)

    def test_idle_cannot_stop(self) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_transition(SessionState.IDLE, SessionState.STOPPED)

    def test_idle_cannot_error(self) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_transition(SessionState.IDLE, SessionState.ERROR)

    def test_all_non_terminal_states_have_outgoing(self) -> None:
        for state in SessionState:
            if state != SessionState.STOPPED:
                assert len(VALID_TRANSITIONS[state]) > 0

    def test_invalid_transition_raises_with_message(self) -> None:
        with pytest.raises(InvalidTransitionError, match="Cannot transition"):
            validate_transition(SessionState.IDLE, SessionState.PAUSED)


# ─── Active Phase ─────────────────────────────────────────────────────────────


class TestActivePhase:
    def test_phase_values(self) -> None:
        assert ActivePhase.THINKING == "thinking"
        assert ActivePhase.GENERATING == "generating"
        assert ActivePhase.TRANSITIONING == "transitioning"


# ─── Message ──────────────────────────────────────────────────────────────────


class TestMessage:
    def test_message_creation(self) -> None:
        msg = Message(type=MessageType.TWIN, content="hello", sender="Shannon")
        assert msg.content == "hello"
        assert msg.sender == "Shannon"
        assert msg.type == MessageType.TWIN
        assert len(msg.id) == 12

    def test_message_to_dict(self) -> None:
        msg = Message(type=MessageType.TWIN, content="hello", sender="Shannon", twin_role="twin_a")
        d = msg.to_dict()
        assert d["type"] == "twin"
        assert d["content"] == "hello"
        assert d["sender"] == "Shannon"
        assert d["twin_role"] == "twin_a"
        assert "timestamp" in d
        assert "id" in d

    def test_message_types(self) -> None:
        assert MessageType.TWIN == "twin"
        assert MessageType.THIRD_AGENT == "third_agent"
        assert MessageType.THOUGHT == "thought"
        assert MessageType.SYSTEM == "system"


# ─── Twin Profile ─────────────────────────────────────────────────────────────


class TestTwinProfile:
    def test_minimal_profile(self) -> None:
        p = TwinProfile(name="Alex", system_prompt="Be Alex.")
        assert p.name == "Alex"
        assert p.avatar == "👤"
        assert p.effective_display_name == "Alex"

    def test_display_name_override(self) -> None:
        p = TwinProfile(name="alex", system_prompt="Be Alex.", display_name="Alex K")
        assert p.effective_display_name == "Alex K"

    def test_to_summary(self) -> None:
        p = TwinProfile(name="Shannon", system_prompt="Be Shannon.", avatar="🌙", color="#C084FC")
        s = p.to_summary()
        assert s["name"] == "Shannon"
        assert s["avatar"] == "🌙"
        assert s["color"] == "#C084FC"

    def test_model_config_defaults(self) -> None:
        p = TwinProfile(name="Test", system_prompt="Test")
        assert p.model.name is None
        assert p.model.temperature is None
        assert p.model.max_tokens is None
        assert p.model.fallback_chain == []

    def test_behavior_config_defaults(self) -> None:
        p = TwinProfile(name="Test", system_prompt="Test")
        assert p.behavior.multi_message is False
        assert p.behavior.max_messages_per_turn == 3
        assert p.behavior.max_message_length == 280

    def test_extra_fields_ignored(self) -> None:
        p = TwinProfile(name="Test", system_prompt="Test", unknown_field="hello")
        assert p.name == "Test"

    def test_memories_list(self) -> None:
        p = TwinProfile(name="Test", system_prompt="Test", memories=["mem1", "mem2"])
        assert len(p.memories) == 2


# ─── Session ──────────────────────────────────────────────────────────────────


class TestSession:
    def test_session_defaults(self) -> None:
        s = Session()
        assert s.state == SessionState.IDLE
        assert s.turn_count == 0
        assert s.current_speaker == "twin_a"
        assert s.messages == []
        assert s.pending_thoughts == []
        assert s.pending_agents == []
        assert len(s.id) == 12

    def test_session_to_dict(self, session: Session) -> None:
        d = session.to_dict()
        assert d["state"] == "idle"
        assert d["turn_count"] == 0
        assert d["twin_a"] is not None
        assert d["twin_b"] is not None
        assert d["pending_thoughts"] == 0

    def test_session_to_dict_no_twins(self) -> None:
        s = Session()
        d = s.to_dict()
        assert d["twin_a"] is None
        assert d["twin_b"] is None
