"""Conversation engine — turn loop, context builder, and response parsing."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING

from doppelchatter.models import (
    ActivePhase,
    Message,
    MessageType,
    Session,
    SessionState,
    TwinProfile,
)

if TYPE_CHECKING:
    from doppelchatter.config import AppConfig
    from doppelchatter.llm import LLMClient
    from doppelchatter.storage import SessionStore
    from doppelchatter.websocket import WebSocketManager

logger = logging.getLogger(__name__)

# Repetition detection — Jaccard similarity threshold
REPETITION_THRESHOLD = 0.85
REPETITION_WINDOW = 4


class ConversationLoop:
    """The core conversation loop. Alternates between twins.

    Sequential asyncio execution guarantees correctness — no concurrent generation.
    """

    def __init__(
        self,
        session: Session,
        config: AppConfig,
        llm_client: LLMClient,
        ws_manager: WebSocketManager,
        storage: SessionStore,
    ) -> None:
        self.session = session
        self.config = config
        self.llm = llm_client
        self.ws = ws_manager
        self.storage = storage
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._stop_requested = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the conversation loop as a background task."""
        self.session.state = SessionState.RUNNING
        self._stop_requested = False
        self._task = asyncio.create_task(self._run())
        await self.ws.broadcast("session_started", {"session": self.session.to_dict()})

    async def _run(self) -> None:
        """Main loop — sequential execution guarantees correctness."""
        session = self.session
        current = self._resolve_first_speaker()

        try:
            while not self._stop_requested:
                # Check max turns
                if 0 < self.config.engine.max_turns <= session.turn_count:
                    break

                # Wait if paused
                await self._pause_event.wait()
                if self._stop_requested:
                    break

                twin = session.twin_a if current == "twin_a" else session.twin_b
                other = session.twin_b if current == "twin_a" else session.twin_a
                if twin is None or other is None:
                    break

                session.current_speaker = current
                session.turn_count += 1

                # Phase: THINKING
                session.active_phase = ActivePhase.THINKING
                await self.ws.broadcast(
                    "thinking_start",
                    {
                        "twin": twin.effective_display_name,
                        "twin_role": current,
                        "turn": session.turn_count,
                    },
                )

                # Drain pending interventions for this twin
                applied_thoughts = [
                    t for t in session.pending_thoughts if t["target"] == current
                ]
                session.pending_thoughts = [
                    t for t in session.pending_thoughts if t["target"] != current
                ]
                applied_agents = list(session.pending_agents)
                session.pending_agents = []

                for thought in applied_thoughts:
                    await self.ws.broadcast(
                        "thought_applied",
                        {
                            "target": current,
                            "text": thought["text"],
                            "turn": session.turn_count,
                        },
                    )

                # Check for repetition and inject nudge if needed
                self._check_repetition(session)

                # Build context
                opening = (
                    str(session.metadata.get("opening_prompt", ""))
                    if session.turn_count == 1
                    else None
                )
                context = build_context(
                    twin=twin,
                    other=other,
                    messages=session.messages,
                    pending_thoughts=applied_thoughts,
                    pending_agents=applied_agents,
                    max_messages=self.config.engine.max_context_messages,
                    opening_prompt=opening,
                )

                # Resolve model parameters
                model = twin.model.name or self.config.llm.default_model
                temperature = (
                    twin.model.temperature
                    if twin.model.temperature is not None
                    else self.config.llm.temperature
                )
                max_tokens = twin.model.max_tokens or self.config.llm.max_tokens
                fallback = twin.model.fallback_chain or list(self.config.llm.fallback_models)

                # Phase: GENERATING
                session.active_phase = ActivePhase.GENERATING
                await self.ws.broadcast(
                    "turn_start",
                    {
                        "twin": twin.effective_display_name,
                        "twin_role": current,
                        "turn": session.turn_count,
                    },
                )

                # Stream from LLM
                full_response = ""
                try:
                    async for token in self.llm.stream(
                        model=model,
                        messages=context,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        fallback_chain=fallback,
                    ):
                        full_response += token
                        await self.ws.broadcast(
                            "stream_token",
                            {"twin_role": current, "token": token},
                        )
                except Exception as e:
                    full_response = await self._handle_generation_error(e, twin)

                # Parse response into message(s)
                messages = parse_response(full_response, twin, current, session.turn_count)

                # Save and broadcast each message
                for msg in messages:
                    session.messages.append(msg)
                    self.storage.append_message(session.id, msg)
                    await self.ws.broadcast(
                        "turn_end",
                        {"message": msg.to_dict(), "turn": session.turn_count},
                    )

                # Phase: TRANSITIONING (inter-turn delay)
                session.active_phase = ActivePhase.TRANSITIONING
                delay = self._calculate_delay()
                await asyncio.sleep(delay)

                # Alternate speaker
                current = "twin_b" if current == "twin_a" else "twin_a"

        except asyncio.CancelledError:
            logger.info(f"Loop cancelled: {session.id}")
        except Exception:
            logger.exception(f"Loop error: {session.id}")
            session.state = SessionState.ERROR
            await self.ws.broadcast(
                "error",
                {
                    "code": "LOOP_ERROR",
                    "message": "Conversation encountered an unexpected error.",
                    "recoverable": True,
                },
            )
        finally:
            if session.state not in (SessionState.ERROR, SessionState.STOPPED):
                session.state = SessionState.STOPPED
            session.active_phase = None
            self.storage.save_session(session)
            await self.ws.broadcast("session_stopped", {"session": session.to_dict()})

    def _resolve_first_speaker(self) -> str:
        speaker = self.config.engine.first_speaker
        if speaker == "random":
            return random.choice(["twin_a", "twin_b"])
        return speaker

    def _calculate_delay(self) -> float:
        cfg = self.config.engine.turn_delay
        if cfg.mode == "fixed":
            return cfg.min_seconds
        return random.uniform(cfg.min_seconds, cfg.max_seconds)

    def _check_repetition(self, session: Session) -> None:
        """Detect repetitive conversation using Jaccard similarity."""
        msgs = [
            m for m in session.messages if m.type == MessageType.TWIN
        ]
        if len(msgs) < REPETITION_WINDOW * 2:
            return

        recent = msgs[-REPETITION_WINDOW:]
        previous = msgs[-REPETITION_WINDOW * 2 : -REPETITION_WINDOW]

        recent_words = set(" ".join(m.content for m in recent).lower().split())
        prev_words = set(" ".join(m.content for m in previous).lower().split())

        if not recent_words or not prev_words:
            return

        intersection = recent_words & prev_words
        union = recent_words | prev_words
        jaccard = len(intersection) / len(union)

        if jaccard >= REPETITION_THRESHOLD:
            session.messages.append(
                Message(
                    type=MessageType.SYSTEM,
                    content="[The conversation feels like it's circling. Push it somewhere new.]",
                    sender="System",
                )
            )
            logger.info(f"Repetition detected (Jaccard={jaccard:.2f}), nudge injected")

    async def _handle_generation_error(self, error: Exception, twin: TwinProfile) -> str:
        """Handle LLM generation errors. Returns response text."""
        logger.error(f"Generation error for {twin.name}: {error}")
        await self.ws.broadcast(
            "error",
            {
                "code": "GENERATION_ERROR",
                "message": f"Lost connection to {twin.effective_display_name}'s thoughts.",
                "recoverable": True,
            },
        )
        return ""

    def pause(self) -> None:
        self._pause_event.clear()
        self.session.state = SessionState.PAUSED
        self.session.active_phase = None

    def resume(self) -> None:
        self._pause_event.set()
        self.session.state = SessionState.RUNNING

    def stop(self) -> None:
        self._stop_requested = True
        self._pause_event.set()
        if self._task:
            self._task.cancel()


# ─── Context Builder ─────────────────────────────────────────────────────────


def build_context(
    twin: TwinProfile,
    other: TwinProfile,
    messages: list[Message],
    pending_thoughts: list[dict[str, str]],
    pending_agents: list[dict[str, str]],
    max_messages: int = 50,
    opening_prompt: str | None = None,
) -> list[dict[str, str]]:
    """Build the LLM context for a twin's turn.

    Structure:
    1. System prompt (personality + background + mood + memories)
    2. Conversation history (sliding window, own=assistant, other=user)
    3. Third agent messages (user role with name prefix)
    4. Thought injection (system role, after history)
    """
    context: list[dict[str, str]] = []

    # 1. System prompt
    system_parts = [twin.system_prompt]
    if twin.background:
        system_parts.append(f"\nBackground: {twin.background}")
    if twin.current_mood:
        system_parts.append(f"\nCurrent mood: {twin.current_mood}")
    if twin.memories:
        memories_text = "\n".join(f"- {m}" for m in twin.memories)
        system_parts.append(f"\nMemories:\n{memories_text}")
    system_parts.append(f"\nYou are talking to {other.effective_display_name}.")
    if opening_prompt:
        system_parts.append(f"\n{opening_prompt}")

    context.append({"role": "system", "content": "\n".join(system_parts)})

    # 2. Conversation history (sliding window)
    history = messages[-max_messages:] if max_messages > 0 else messages

    for msg in history:
        if msg.type == MessageType.TWIN:
            if msg.sender == twin.effective_display_name:
                context.append({"role": "assistant", "content": msg.content})
            else:
                context.append(
                    {"role": "user", "content": f"{msg.sender}: {msg.content}"}
                )
        elif msg.type == MessageType.THIRD_AGENT:
            context.append(
                {"role": "user", "content": f"{msg.sender}: {msg.content}"}
            )
        # THOUGHT and SYSTEM messages from history are NOT re-injected

    # 3. Pending third-agent messages
    for agent_msg in pending_agents:
        context.append(
            {"role": "user", "content": f"{agent_msg['name']}: {agent_msg['text']}"}
        )

    # 4. Pending thoughts (as system message — invisible to other twin)
    if pending_thoughts:
        if len(pending_thoughts) == 1:
            thought_text = f"[Inner voice: {pending_thoughts[0]['text']}]"
        else:
            parts = "\n".join(f"- {t['text']}" for t in pending_thoughts)
            thought_text = f"[Thoughts running through your mind:\n{parts}]"
        context.append({"role": "system", "content": thought_text})

    return context


# ─── Response Parsing ─────────────────────────────────────────────────────────


def parse_response(
    response: str,
    twin: TwinProfile,
    twin_role: str,
    turn_number: int,
) -> list[Message]:
    """Parse LLM response into Message(s).

    If multi_message is enabled, split on double newlines to simulate burst-texting.
    """
    text = response.strip()
    if not text:
        text = "..."

    if not twin.behavior.multi_message:
        return [
            Message(
                type=MessageType.TWIN,
                content=text,
                sender=twin.effective_display_name,
                twin_role=twin_role,
                turn_number=turn_number,
            )
        ]

    # Split into multiple messages
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    max_msgs = twin.behavior.max_messages_per_turn
    if len(parts) > max_msgs:
        parts = parts[: max_msgs - 1] + ["\n\n".join(parts[max_msgs - 1 :])]

    return [
        Message(
            type=MessageType.TWIN,
            content=part,
            sender=twin.effective_display_name,
            twin_role=twin_role,
            turn_number=turn_number,
            metadata={"sequence": i},
        )
        for i, part in enumerate(parts)
    ]
