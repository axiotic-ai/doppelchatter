"""Intervention system — thought injection and third agent."""

from __future__ import annotations

import uuid

from doppelchatter.models import Message, MessageType, Session

THOUGHT_QUEUE_CAP = 10
THOUGHT_MAX_LENGTH = 500
AGENT_NAME_MAX_LENGTH = 50
AGENT_TEXT_MAX_LENGTH = 1000


def inject_thought(session: Session, target: str, text: str) -> dict[str, str] | None:
    """Queue a thought for a target twin.

    Returns the thought dict, or None if queue is full (cap: 10).
    """
    target_count = sum(1 for t in session.pending_thoughts if t["target"] == target)
    if target_count >= THOUGHT_QUEUE_CAP:
        return None

    clean_text = text.strip()[:THOUGHT_MAX_LENGTH]
    thought: dict[str, str] = {
        "id": uuid.uuid4().hex[:8],
        "target": target,
        "text": clean_text,
    }
    session.pending_thoughts.append(thought)

    # Record in transcript (visible in export, not re-injected into context)
    target_twin = session.twin_a if target == "twin_a" else session.twin_b
    target_name = target_twin.effective_display_name if target_twin else target
    session.messages.append(
        Message(
            type=MessageType.THOUGHT,
            content=clean_text,
            sender="Director",
            metadata={"target": target, "target_name": target_name},
        )
    )

    return thought


def inject_third_agent(session: Session, name: str, text: str) -> dict[str, str]:
    """Queue a third-agent message. Visible to both twins on next turn."""
    clean_name = name.strip()[:AGENT_NAME_MAX_LENGTH]
    clean_text = text.strip()[:AGENT_TEXT_MAX_LENGTH]

    agent_msg: dict[str, str] = {
        "id": uuid.uuid4().hex[:8],
        "name": clean_name,
        "text": clean_text,
    }
    session.pending_agents.append(agent_msg)

    # Record in transcript
    session.messages.append(
        Message(
            type=MessageType.THIRD_AGENT,
            content=clean_text,
            sender=clean_name,
        )
    )

    return agent_msg


def cancel_thought(session: Session, thought_id: str) -> bool:
    """Cancel a pending thought. Returns True if found and removed."""
    before = len(session.pending_thoughts)
    session.pending_thoughts = [
        t for t in session.pending_thoughts if t["id"] != thought_id
    ]
    return len(session.pending_thoughts) < before
