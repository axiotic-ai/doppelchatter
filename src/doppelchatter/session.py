"""Session controller — orchestrates state, engine, and interventions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from doppelchatter.config import AppConfig, load_profiles, load_scenarios
from doppelchatter.engine import ConversationLoop
from doppelchatter.interventions import cancel_thought, inject_third_agent, inject_thought
from doppelchatter.models import (
    ProfileNotFoundError,
    Session,
    SessionState,
    TwinProfile,
)

if TYPE_CHECKING:
    from doppelchatter.llm import LLMClient
    from doppelchatter.storage import SessionStore
    from doppelchatter.websocket import WebSocketManager

logger = logging.getLogger(__name__)


class SessionController:
    """Manages the active session, routing commands to the engine."""

    def __init__(
        self,
        config: AppConfig,
        llm_client: LLMClient,
        ws_manager: WebSocketManager,
        storage: SessionStore,
    ) -> None:
        self.config = config
        self.llm = llm_client
        self.ws = ws_manager
        self.storage = storage
        self.profiles: dict[str, TwinProfile] = {}
        self.scenarios: dict[str, dict[str, object]] = {}
        self.session: Session | None = None
        self._loop: ConversationLoop | None = None

    def load_data(self) -> None:
        """Load profiles and scenarios from disk."""
        self.profiles = load_profiles(Path(self.config.twins_dir))
        self.scenarios = load_scenarios(Path(self.config.scenarios_dir))
        logger.info(
            f"Loaded {len(self.profiles)} profiles, {len(self.scenarios)} scenarios"
        )

    async def start_session(
        self,
        twin_a_slug: str,
        twin_b_slug: str,
        scenario_slug: str = "",
        scenario_text: str = "",
    ) -> Session:
        """Create and start a new session."""
        # Stop existing session if any
        if self.session and self.session.state in (
            SessionState.RUNNING,
            SessionState.PAUSED,
        ):
            await self.stop()

        # Resolve profiles
        profile_a = self.profiles.get(twin_a_slug)
        profile_b = self.profiles.get(twin_b_slug)
        if not profile_a:
            raise ProfileNotFoundError(f"Twin profile not found: {twin_a_slug}")
        if not profile_b:
            raise ProfileNotFoundError(f"Twin profile not found: {twin_b_slug}")

        # Create session
        session = Session()
        session.twin_a = profile_a.model_copy()
        session.twin_b = profile_b.model_copy()

        # Apply scenario overrides
        if scenario_slug and scenario_slug in self.scenarios:
            scenario = self.scenarios[scenario_slug]
            session.scenario_name = str(scenario.get("name", scenario_slug))
            self._apply_scenario(session, scenario)
        elif scenario_text:
            session.scenario_text = scenario_text

        self.session = session
        self.storage.save_session(session)

        # Start engine
        self._loop = ConversationLoop(
            session=session,
            config=self.config,
            llm_client=self.llm,
            ws_manager=self.ws,
            storage=self.storage,
        )
        await self._loop.start()

        logger.info(
            f"Session {session.id} started: "
            f"{profile_a.effective_display_name} × {profile_b.effective_display_name}"
        )
        return session

    def _apply_scenario(self, session: Session, scenario: dict[str, object]) -> None:
        """Apply scenario overrides to session twins."""
        context = scenario.get("context", {})
        if not isinstance(context, dict):
            return

        # Apply to twin A
        ctx_a = context.get("a", {})
        if isinstance(ctx_a, dict) and session.twin_a:
            if "current_mood" in ctx_a:
                session.twin_a = session.twin_a.model_copy(
                    update={"current_mood": ctx_a["current_mood"]}
                )
            if "memories" in ctx_a and isinstance(ctx_a["memories"], list):
                existing = list(session.twin_a.memories)
                existing.extend(ctx_a["memories"])
                session.twin_a = session.twin_a.model_copy(update={"memories": existing})

        # Apply to twin B
        ctx_b = context.get("b", {})
        if isinstance(ctx_b, dict) and session.twin_b:
            if "current_mood" in ctx_b:
                session.twin_b = session.twin_b.model_copy(
                    update={"current_mood": ctx_b["current_mood"]}
                )
            if "memories" in ctx_b and isinstance(ctx_b["memories"], list):
                existing = list(session.twin_b.memories)
                existing.extend(ctx_b["memories"])
                session.twin_b = session.twin_b.model_copy(update={"memories": existing})

        # Store opening prompt
        opening = scenario.get("opening_prompt")
        if opening:
            session.metadata["opening_prompt"] = opening

    async def pause(self) -> None:
        """Pause the active session."""
        if self._loop and self.session and self.session.state == SessionState.RUNNING:
            self._loop.pause()
            self.storage.save_session(self.session)
            await self.ws.broadcast("session_paused", {"session": self.session.to_dict()})
            logger.info(f"Session {self.session.id} paused")

    async def resume(self) -> None:
        """Resume the active session."""
        if self._loop and self.session and self.session.state == SessionState.PAUSED:
            self._loop.resume()
            self.storage.save_session(self.session)
            await self.ws.broadcast("session_resumed", {"session": self.session.to_dict()})
            logger.info(f"Session {self.session.id} resumed")

    async def stop(self) -> None:
        """Stop the active session."""
        if self._loop and self.session and self.session.state in (
            SessionState.RUNNING,
            SessionState.PAUSED,
            SessionState.ERROR,
        ):
            self._loop.stop()
            self.session.state = SessionState.STOPPED
            self.storage.save_session(self.session)
            logger.info(f"Session {self.session.id} stopped")

    async def handle_thought(self, target: str, text: str) -> dict[str, object]:
        """Handle thought injection request."""
        if not self.session:
            return {"error": "No active session"}
        result = inject_thought(self.session, target, text)
        if result is None:
            return {"error": "Thought queue full. Let some land first."}
        self.storage.append_message(self.session.id, self.session.messages[-1])
        await self.ws.broadcast("thought_queued", {"thought": result})
        return {"thought": result}

    async def handle_third_agent(self, name: str, text: str) -> dict[str, object]:
        """Handle third agent injection request."""
        if not self.session:
            return {"error": "No active session"}
        result = inject_third_agent(self.session, name, text)
        self.storage.append_message(self.session.id, self.session.messages[-1])
        await self.ws.broadcast("agent_delivered", {"message": result})
        return {"agent": result}

    async def handle_cancel_thought(self, thought_id: str) -> dict[str, object]:
        """Cancel a pending thought."""
        if not self.session:
            return {"error": "No active session"}
        removed = cancel_thought(self.session, thought_id)
        if removed:
            await self.ws.broadcast("thought_cancelled", {"thought_id": thought_id})
        return {"cancelled": removed}
