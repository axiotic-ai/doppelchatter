"""Tests for the intervention system — thoughts, third agents, cancellation."""

from __future__ import annotations

from doppelchatter.interventions import (
    AGENT_NAME_MAX_LENGTH,
    AGENT_TEXT_MAX_LENGTH,
    THOUGHT_MAX_LENGTH,
    THOUGHT_QUEUE_CAP,
    cancel_thought,
    inject_third_agent,
    inject_thought,
)
from doppelchatter.models import MessageType, Session


class TestInjectThought:
    def test_thought_queued(self, session: Session) -> None:
        thought = inject_thought(session, "twin_a", "Tell the truth")
        assert thought is not None
        assert len(session.pending_thoughts) == 1
        assert thought["text"] == "Tell the truth"
        assert thought["target"] == "twin_a"

    def test_thought_has_id(self, session: Session) -> None:
        thought = inject_thought(session, "twin_a", "Test")
        assert thought is not None
        assert len(thought["id"]) == 8

    def test_thought_recorded_in_transcript(self, session: Session) -> None:
        inject_thought(session, "twin_a", "Be honest")
        thought_msgs = [m for m in session.messages if m.type == MessageType.THOUGHT]
        assert len(thought_msgs) == 1
        assert thought_msgs[0].content == "Be honest"
        assert thought_msgs[0].sender == "Director"

    def test_thought_transcript_metadata(self, session: Session) -> None:
        inject_thought(session, "twin_a", "Test")
        msg = session.messages[-1]
        assert msg.metadata["target"] == "twin_a"
        assert msg.metadata["target_name"] == "Shannon"

    def test_thought_truncated_at_max_length(self, session: Session) -> None:
        long_text = "x" * 1000
        thought = inject_thought(session, "twin_a", long_text)
        assert thought is not None
        assert len(thought["text"]) == THOUGHT_MAX_LENGTH

    def test_thought_stripped(self, session: Session) -> None:
        thought = inject_thought(session, "twin_a", "  padded  ")
        assert thought is not None
        assert thought["text"] == "padded"

    def test_queue_cap_at_10(self, session: Session) -> None:
        for i in range(THOUGHT_QUEUE_CAP):
            result = inject_thought(session, "twin_a", f"Thought {i}")
            assert result is not None
        overflow = inject_thought(session, "twin_a", "One too many")
        assert overflow is None
        a_thoughts = [t for t in session.pending_thoughts if t["target"] == "twin_a"]
        assert len(a_thoughts) == THOUGHT_QUEUE_CAP

    def test_per_twin_isolation(self, session: Session) -> None:
        inject_thought(session, "twin_a", "For A")
        inject_thought(session, "twin_b", "For B")
        a_thoughts = [t for t in session.pending_thoughts if t["target"] == "twin_a"]
        b_thoughts = [t for t in session.pending_thoughts if t["target"] == "twin_b"]
        assert len(a_thoughts) == 1
        assert len(b_thoughts) == 1
        assert a_thoughts[0]["text"] == "For A"
        assert b_thoughts[0]["text"] == "For B"

    def test_per_twin_cap_independent(self, session: Session) -> None:
        """Filling twin_a's queue shouldn't block twin_b."""
        for i in range(THOUGHT_QUEUE_CAP):
            inject_thought(session, "twin_a", f"A{i}")
        result = inject_thought(session, "twin_b", "B thought")
        assert result is not None

    def test_thought_consumed_on_drain(self, session: Session) -> None:
        inject_thought(session, "twin_a", "T1")
        inject_thought(session, "twin_a", "T2")
        # Simulate drain (as conversation loop does)
        applied = [t for t in session.pending_thoughts if t["target"] == "twin_a"]
        session.pending_thoughts = [
            t for t in session.pending_thoughts if t["target"] != "twin_a"
        ]
        assert len(applied) == 2
        assert len(session.pending_thoughts) == 0


class TestCancelThought:
    def test_cancel_existing(self, session: Session) -> None:
        thought = inject_thought(session, "twin_a", "Cancel me")
        assert thought is not None
        assert cancel_thought(session, thought["id"])
        assert len(session.pending_thoughts) == 0

    def test_cancel_nonexistent(self, session: Session) -> None:
        assert not cancel_thought(session, "nonexistent")

    def test_cancel_specific_thought(self, session: Session) -> None:
        t1 = inject_thought(session, "twin_a", "Keep me")
        t2 = inject_thought(session, "twin_a", "Remove me")
        assert t1 is not None and t2 is not None
        cancel_thought(session, t2["id"])
        assert len(session.pending_thoughts) == 1
        assert session.pending_thoughts[0]["text"] == "Keep me"


class TestInjectThirdAgent:
    def test_agent_queued(self, session: Session) -> None:
        agent = inject_third_agent(session, "Mike", "Hey both!")
        assert agent["name"] == "Mike"
        assert agent["text"] == "Hey both!"
        assert len(session.pending_agents) == 1

    def test_agent_has_id(self, session: Session) -> None:
        agent = inject_third_agent(session, "Mike", "Hey")
        assert len(agent["id"]) == 8

    def test_agent_recorded_in_transcript(self, session: Session) -> None:
        inject_third_agent(session, "Mike", "Hello!")
        agent_msgs = [m for m in session.messages if m.type == MessageType.THIRD_AGENT]
        assert len(agent_msgs) == 1
        assert agent_msgs[0].sender == "Mike"
        assert agent_msgs[0].content == "Hello!"

    def test_agent_name_truncated(self, session: Session) -> None:
        long_name = "A" * 100
        agent = inject_third_agent(session, long_name, "Hi")
        assert len(agent["name"]) == AGENT_NAME_MAX_LENGTH

    def test_agent_text_truncated(self, session: Session) -> None:
        long_text = "B" * 2000
        agent = inject_third_agent(session, "Mike", long_text)
        assert len(agent["text"]) == AGENT_TEXT_MAX_LENGTH

    def test_agent_stripped(self, session: Session) -> None:
        agent = inject_third_agent(session, "  Mike  ", "  Hello  ")
        assert agent["name"] == "Mike"
        assert agent["text"] == "Hello"
