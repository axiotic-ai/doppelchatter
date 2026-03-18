"""Tests for the conversation engine — context builder and response parsing."""

from __future__ import annotations

from doppelchatter.engine import build_context, parse_response
from doppelchatter.models import (
    BehaviorConfig,
    Message,
    MessageType,
    TwinProfile,
)


class TestBuildContext:
    def test_system_prompt_includes_personality(
        self, shannon: TwinProfile, antreas: TwinProfile
    ) -> None:
        context = build_context(shannon, antreas, [], [], [], 50)
        assert context[0]["role"] == "system"
        assert "Shannon" in context[0]["content"]

    def test_system_prompt_includes_background(self) -> None:
        twin = TwinProfile(
            name="Test",
            system_prompt="Be test.",
            background="Has a cat named Muffin.",
        )
        other = TwinProfile(name="Other", system_prompt="Be other.")
        context = build_context(twin, other, [], [], [], 50)
        assert "Muffin" in context[0]["content"]

    def test_system_prompt_includes_mood(self) -> None:
        twin = TwinProfile(
            name="Test", system_prompt="Be test.", current_mood="Sleepy"
        )
        other = TwinProfile(name="Other", system_prompt="Be other.")
        context = build_context(twin, other, [], [], [], 50)
        assert "Sleepy" in context[0]["content"]

    def test_system_prompt_includes_memories(self) -> None:
        twin = TwinProfile(
            name="Test", system_prompt="Be test.", memories=["Went to Japan"]
        )
        other = TwinProfile(name="Other", system_prompt="Be other.")
        context = build_context(twin, other, [], [], [], 50)
        assert "Japan" in context[0]["content"]

    def test_system_prompt_includes_other_name(
        self, shannon: TwinProfile, antreas: TwinProfile
    ) -> None:
        context = build_context(shannon, antreas, [], [], [], 50)
        assert "Antreas" in context[0]["content"]

    def test_own_messages_are_assistant_role(
        self,
        shannon: TwinProfile,
        antreas: TwinProfile,
        conversation: list[Message],
    ) -> None:
        context = build_context(shannon, antreas, conversation, [], [], 50)
        assistant_msgs = [m for m in context if m["role"] == "assistant"]
        assert len(assistant_msgs) > 0
        assert all("Shannon" not in m["content"] for m in assistant_msgs)

    def test_other_messages_are_user_role_with_prefix(
        self,
        shannon: TwinProfile,
        antreas: TwinProfile,
        conversation: list[Message],
    ) -> None:
        context = build_context(shannon, antreas, conversation, [], [], 50)
        user_msgs = [m for m in context if m["role"] == "user"]
        assert len(user_msgs) > 0
        assert all("Antreas:" in m["content"] for m in user_msgs)

    def test_thoughts_injected_as_system_message(
        self,
        shannon: TwinProfile,
        antreas: TwinProfile,
        conversation: list[Message],
    ) -> None:
        thoughts = [{"id": "t1", "target": "twin_a", "text": "Tell the truth"}]
        context = build_context(shannon, antreas, conversation, thoughts, [], 50)
        system_msgs = [m for m in context if m["role"] == "system"]
        assert any("Inner voice" in m["content"] for m in system_msgs)

    def test_multiple_thoughts_formatted(
        self,
        shannon: TwinProfile,
        antreas: TwinProfile,
    ) -> None:
        thoughts = [
            {"id": "t1", "target": "twin_a", "text": "First thought"},
            {"id": "t2", "target": "twin_a", "text": "Second thought"},
        ]
        context = build_context(shannon, antreas, [], thoughts, [], 50)
        system_msgs = [m for m in context if m["role"] == "system"]
        thought_msg = [m for m in system_msgs if "Thoughts running" in m["content"]]
        assert len(thought_msg) == 1
        assert "First thought" in thought_msg[0]["content"]
        assert "Second thought" in thought_msg[0]["content"]

    def test_thoughts_invisible_to_other_twin(
        self,
        shannon: TwinProfile,
        antreas: TwinProfile,
        conversation: list[Message],
    ) -> None:
        """Thoughts for Shannon must NOT appear in Antreas's context."""
        # Build context for Antreas (other twin) — no thoughts passed
        context = build_context(antreas, shannon, conversation, [], [], 50)
        all_content = " ".join(m["content"] for m in context)
        assert "Secret" not in all_content

    def test_third_agent_in_context(
        self,
        shannon: TwinProfile,
        antreas: TwinProfile,
    ) -> None:
        agents = [{"name": "Mike", "text": "Hey both!"}]
        context = build_context(shannon, antreas, [], [], agents, 50)
        user_msgs = [m for m in context if m["role"] == "user"]
        assert any("Mike: Hey both!" in m["content"] for m in user_msgs)

    def test_third_agent_visible_to_both(
        self,
        shannon: TwinProfile,
        antreas: TwinProfile,
    ) -> None:
        agents = [{"name": "Mike", "text": "Hey both!"}]
        ctx_a = build_context(shannon, antreas, [], [], agents, 50)
        ctx_b = build_context(antreas, shannon, [], [], agents, 50)
        assert any("Mike" in m["content"] for m in ctx_a)
        assert any("Mike" in m["content"] for m in ctx_b)

    def test_sliding_window_trims_old_messages(
        self,
        shannon: TwinProfile,
        antreas: TwinProfile,
    ) -> None:
        msgs = [
            Message(
                type=MessageType.TWIN,
                content=f"msg{i}",
                sender="Shannon" if i % 2 == 0 else "Antreas",
                twin_role="twin_a" if i % 2 == 0 else "twin_b",
            )
            for i in range(100)
        ]
        context = build_context(shannon, antreas, msgs, [], [], max_messages=10)
        conv_msgs = [m for m in context if m["role"] in ("user", "assistant")]
        assert len(conv_msgs) == 10

    def test_opening_prompt_included(
        self,
        shannon: TwinProfile,
        antreas: TwinProfile,
    ) -> None:
        context = build_context(
            shannon, antreas, [], [], [], 50, opening_prompt="Start with a joke."
        )
        assert "Start with a joke" in context[0]["content"]

    def test_thought_and_system_messages_from_history_not_reinjected(
        self,
        shannon: TwinProfile,
        antreas: TwinProfile,
    ) -> None:
        msgs = [
            Message(type=MessageType.THOUGHT, content="Secret thought", sender="Director"),
            Message(type=MessageType.SYSTEM, content="System nudge", sender="System"),
            Message(type=MessageType.TWIN, content="hello", sender="Shannon", twin_role="twin_a"),
        ]
        context = build_context(shannon, antreas, msgs, [], [], 50)
        # Only the twin message and system prompt should appear
        non_system = [m for m in context if m["role"] != "system"]
        assert len(non_system) == 1  # just the assistant message
        # The thought and system message from history should NOT be reinjected
        all_content = " ".join(m["content"] for m in context)
        assert "Secret thought" not in all_content
        assert "System nudge" not in all_content

    def test_empty_conversation(
        self,
        shannon: TwinProfile,
        antreas: TwinProfile,
    ) -> None:
        context = build_context(shannon, antreas, [], [], [], 50)
        assert len(context) == 1  # Just system prompt
        assert context[0]["role"] == "system"


class TestParseResponse:
    def test_single_message(self, shannon: TwinProfile) -> None:
        msgs = parse_response("hello x", shannon, "twin_a", 1)
        assert len(msgs) == 1
        assert msgs[0].content == "hello x"
        assert msgs[0].sender == "Shannon"
        assert msgs[0].twin_role == "twin_a"

    def test_empty_response_becomes_ellipsis(self, shannon: TwinProfile) -> None:
        msgs = parse_response("", shannon, "twin_a", 1)
        assert msgs[0].content == "..."

    def test_whitespace_response_becomes_ellipsis(self, shannon: TwinProfile) -> None:
        msgs = parse_response("   \n  ", shannon, "twin_a", 1)
        assert msgs[0].content == "..."

    def test_multi_message_split(self) -> None:
        twin = TwinProfile(
            name="Test",
            system_prompt="Test",
            behavior=BehaviorConfig(multi_message=True, max_messages_per_turn=3),
        )
        response = "first message\n\nsecond message\n\nthird message"
        msgs = parse_response(response, twin, "twin_a", 1)
        assert len(msgs) == 3
        assert msgs[0].content == "first message"
        assert msgs[1].content == "second message"
        assert msgs[2].content == "third message"

    def test_multi_message_overflow_merged(self) -> None:
        twin = TwinProfile(
            name="Test",
            system_prompt="Test",
            behavior=BehaviorConfig(multi_message=True, max_messages_per_turn=2),
        )
        response = "first\n\nsecond\n\nthird\n\nfourth"
        msgs = parse_response(response, twin, "twin_a", 1)
        assert len(msgs) == 2
        assert msgs[0].content == "first"
        assert "second" in msgs[1].content
        assert "third" in msgs[1].content
        assert "fourth" in msgs[1].content

    def test_multi_message_disabled(self, shannon: TwinProfile) -> None:
        response = "one\n\ntwo\n\nthree"
        msgs = parse_response(response, shannon, "twin_a", 1)
        assert len(msgs) == 1
        assert "one" in msgs[0].content

    def test_sequence_metadata(self) -> None:
        twin = TwinProfile(
            name="Test",
            system_prompt="Test",
            behavior=BehaviorConfig(multi_message=True),
        )
        response = "first\n\nsecond"
        msgs = parse_response(response, twin, "twin_a", 1)
        assert msgs[0].metadata.get("sequence") == 0
        assert msgs[1].metadata.get("sequence") == 1
