"""FastAPI application factory — REST API, WebSocket handler, static files."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from doppelchatter import __version__
from doppelchatter.config import AppConfig
from doppelchatter.llm import LLMClient
from doppelchatter.session import SessionController
from doppelchatter.storage import (
    SessionStore,
    check_unclean_shutdown,
    export_html,
    export_json,
    export_markdown,
)
from doppelchatter.websocket import WebSocketManager

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: AppConfig) -> FastAPI:
    """Create and configure the FastAPI application."""
    ws_manager = WebSocketManager()
    storage = SessionStore(Path(config.sessions_dir))
    llm_client = LLMClient(
        api_key=config.llm.api_key,
        anthropic_api_key=config.llm.anthropic_api_key,
        timeout=config.llm.timeout_seconds,
    )
    controller = SessionController(
        config=config,
        llm_client=llm_client,
        ws_manager=ws_manager,
        storage=storage,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Startup
        check_unclean_shutdown(Path(config.sessions_dir))
        controller.load_data()
        profile_names = ", ".join(controller.profiles.keys()) or "(none)"
        logger.info(f"Profiles loaded: {profile_names}")
        yield
        # Shutdown
        await llm_client.close()

    app = FastAPI(
        title="Doppelchatter",
        version=__version__,
        lifespan=lifespan,
    )

    # Store controller on app state for access in route handlers
    app.state.controller = controller  # type: ignore[attr-defined]

    # ─── Frontend ─────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def serve_frontend() -> HTMLResponse:
        index = STATIC_DIR / "index.html"
        if index.exists():
            return HTMLResponse(content=index.read_text())
        return HTMLResponse(content="<h1>Doppelchatter</h1><p>Frontend not found.</p>")

    # ─── REST API ─────────────────────────────────────────────────────────

    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        session_info = None
        if controller.session:
            session_info = {
                "id": controller.session.id,
                "state": controller.session.state.value,
                "turn_count": controller.session.turn_count,
            }
        return {
            "status": "ok",
            "version": __version__,
            "active_session": session_info,
        }

    @app.get("/api/v1/profiles")
    async def list_profiles() -> list[dict[str, str]]:
        return [
            {"slug": slug, **profile.to_summary()}
            for slug, profile in controller.profiles.items()
        ]

    @app.get("/api/v1/profiles/{slug}")
    async def get_profile(slug: str) -> Response:
        profile = controller.profiles.get(slug)
        if not profile:
            return JSONResponse({"error": f"Profile not found: {slug}"}, status_code=404)
        return JSONResponse({
            "slug": slug,
            **profile.to_summary(),
            "system_prompt": profile.system_prompt[:100] + "...",
            "background": profile.background,
            "tags": profile.tags,
        })

    @app.get("/api/v1/scenarios")
    async def list_scenarios() -> list[dict[str, object]]:
        return [
            {
                "slug": slug,
                "name": scenario.get("name", slug),
                "description": scenario.get("description", ""),
                "twins": scenario.get("twins", {}),
            }
            for slug, scenario in controller.scenarios.items()
        ]

    @app.get("/api/v1/sessions")
    async def list_sessions() -> list[dict[str, object]]:
        return storage.list_sessions()

    @app.get("/api/v1/sessions/{session_id}/export")
    async def export_session(
        session_id: str,
        format: str = Query(default="json", pattern="^(json|markdown|html)$"),
    ) -> Response:
        data = storage.load_session(session_id)
        if not data:
            return JSONResponse({"error": "Session not found"}, status_code=404)

        if format == "markdown":
            return PlainTextResponse(
                export_markdown(data),
                media_type="text/markdown",
                headers={"Content-Disposition": f"attachment; filename={session_id}.md"},
            )
        elif format == "html":
            return HTMLResponse(
                export_html(data),
                headers={"Content-Disposition": f"attachment; filename={session_id}.html"},
            )
        else:
            return JSONResponse(
                json.loads(export_json(data)),
                headers={"Content-Disposition": f"attachment; filename={session_id}.json"},
            )

    # ─── WebSocket ────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws_manager.connect(ws)

        # Send initial state
        profiles_data = [
            {"slug": slug, **p.to_summary()}
            for slug, p in controller.profiles.items()
        ]
        scenarios_data = [
            {"slug": slug, "name": s.get("name", slug), "description": s.get("description", "")}
            for slug, s in controller.scenarios.items()
        ]
        session_data = controller.session.to_dict() if controller.session else None

        await ws_manager.send(ws, "connected", {
            "server_version": __version__,
            "session": session_data,
            "profiles": profiles_data,
            "scenarios": scenarios_data,
            "sequence": ws_manager.sequence,
        })

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws_manager.send(ws, "error", {"message": "Invalid JSON"})
                    continue

                msg_type = msg.get("type", "")
                await _handle_ws_message(controller, ws_manager, ws, msg_type, msg)

        except WebSocketDisconnect:
            ws_manager.disconnect(ws)
        except Exception:
            logger.exception("WebSocket error")
            ws_manager.disconnect(ws)

    return app


async def _handle_ws_message(
    controller: SessionController,
    ws_manager: WebSocketManager,
    ws: WebSocket,
    msg_type: str,
    msg: dict[str, object],
) -> None:
    """Route WebSocket messages to the appropriate handler."""
    match msg_type:
        case "start_session":
            try:
                await controller.start_session(
                    twin_a_slug=str(msg.get("twin_a", "")),
                    twin_b_slug=str(msg.get("twin_b", "")),
                    scenario_slug=str(msg.get("scenario", "")),
                    scenario_text=str(msg.get("scenario_text", "")),
                )
            except Exception as e:
                await ws_manager.send(ws, "error", {
                    "code": "SESSION_ERROR",
                    "message": str(e),
                    "recoverable": True,
                })

        case "pause":
            await controller.pause()

        case "resume":
            await controller.resume()

        case "stop":
            await controller.stop()

        case "inject_thought":
            result = await controller.handle_thought(
                target=str(msg.get("target", "")),
                text=str(msg.get("text", "")),
            )
            if "error" in result:
                await ws_manager.send(ws, "error", {
                    "code": "QUEUE_FULL",
                    "message": str(result["error"]),
                    "recoverable": True,
                })

        case "inject_agent":
            await controller.handle_third_agent(
                name=str(msg.get("name", "")),
                text=str(msg.get("text", "")),
            )

        case "cancel_thought":
            await controller.handle_cancel_thought(
                thought_id=str(msg.get("thought_id", "")),
            )

        case "resync":
            last_seq = int(msg.get("last_sequence", 0))  # type: ignore[arg-type]
            await ws_manager.resync(ws, last_seq)

        case "ping":
            await ws_manager.send(ws, "pong")

        case _:
            logger.debug(f"Unknown WS message type: {msg_type}")
