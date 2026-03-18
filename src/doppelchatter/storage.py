"""JSONL persistence and transcript export."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from doppelchatter.models import Message, Session

logger = logging.getLogger(__name__)


class SessionStore:
    """Persists sessions as JSON + JSONL files."""

    def __init__(self, sessions_dir: Path) -> None:
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session: Session) -> None:
        """Save session metadata."""
        session_dir = self._dir / session.id
        session_dir.mkdir(exist_ok=True)
        (session_dir / "session.json").write_text(
            json.dumps(session.to_dict(), indent=2, ensure_ascii=False, default=str)
        )

    def append_message(self, session_id: str, message: Message) -> None:
        """Append a single message (fast, incremental)."""
        session_dir = self._dir / session_id
        session_dir.mkdir(exist_ok=True)
        with open(session_dir / "messages.jsonl", "a") as f:
            f.write(json.dumps(message.to_dict(), ensure_ascii=False, default=str) + "\n")

    def load_session(self, session_id: str) -> dict[str, object] | None:
        """Load session metadata + all messages."""
        session_dir = self._dir / session_id
        meta_path = session_dir / "session.json"
        if not meta_path.exists():
            return None

        data: dict[str, object] = json.loads(meta_path.read_text())
        messages: list[dict[str, object]] = []
        msgs_path = session_dir / "messages.jsonl"
        if msgs_path.exists():
            for line in msgs_path.read_text().splitlines():
                if line.strip():
                    messages.append(json.loads(line))
        data["messages"] = messages
        return data

    def list_sessions(self) -> list[dict[str, object]]:
        """List all stored sessions (metadata only, newest first)."""
        sessions: list[dict[str, object]] = []
        if not self._dir.exists():
            return sessions
        for d in sorted(self._dir.iterdir(), reverse=True):
            meta = d / "session.json"
            if meta.exists():
                try:
                    sessions.append(json.loads(meta.read_text()))
                except json.JSONDecodeError:
                    logger.warning(f"Corrupt session metadata: {meta}")
        return sessions


def check_unclean_shutdown(sessions_dir: Path) -> None:
    """Mark interrupted sessions as stopped.

    If a session was RUNNING when the server crashed, it can't be
    safely resumed (LLM state is lost). Mark as STOPPED.
    """
    if not sessions_dir.exists():
        return
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        meta_path = session_dir / "session.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            continue
        if meta.get("state") not in ("idle", "stopped"):
            meta["state"] = "stopped"
            if "metadata" not in meta:
                meta["metadata"] = {}
            meta["metadata"]["unclean_shutdown"] = True  # type: ignore[index]
            meta_path.write_text(json.dumps(meta, indent=2))
            logger.info(f"Marked crashed session {session_dir.name} as stopped")


# ─── Export Functions ─────────────────────────────────────────────────────────


def export_json(session_data: dict[str, object]) -> str:
    """Export session as formatted JSON."""
    return json.dumps(session_data, indent=2, ensure_ascii=False, default=str)


def export_markdown(session_data: dict[str, object]) -> str:
    """Export session as readable Markdown."""
    twin_a = session_data.get("twin_a", {}) or {}
    twin_b = session_data.get("twin_b", {}) or {}
    name_a = twin_a.get("display_name", "Twin A") if isinstance(twin_a, dict) else "Twin A"
    name_b = twin_b.get("display_name", "Twin B") if isinstance(twin_b, dict) else "Twin B"

    lines = [
        f"# {name_a} × {name_b}",
        f"**Session:** {session_data.get('id', 'unknown')}",
        f"**Date:** {str(session_data.get('created_at', ''))[:10]}",
        f"**Turns:** {session_data.get('turn_count', 0)}",
        f"**Messages:** {len(session_data.get('messages', []))}",  # type: ignore[arg-type]
        "",
        "---",
        "",
    ]

    messages = session_data.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        msg_type = msg.get("type", "")
        sender = msg.get("sender", "")
        content = msg.get("content", "")

        if msg_type == "twin":
            lines.append(f"**{sender}**")
            lines.append(content)
            lines.append("")
        elif msg_type == "thought":
            target_name = msg.get("metadata", {}).get("target_name", "?")
            lines.append(f"> 💭 *[Thought → {target_name}]* {content}")
            lines.append("")
        elif msg_type == "third_agent":
            lines.append(f"**🎭 {sender}**")
            lines.append(content)
            lines.append("")
        elif msg_type == "system":
            lines.append(f"*{content}*")
            lines.append("")

    lines.extend(["---", "*Exported from Doppelchatter*"])
    return "\n".join(lines)


def export_html(session_data: dict[str, object]) -> str:
    """Export session as self-contained dark-themed HTML document."""
    twin_a = session_data.get("twin_a", {}) or {}
    twin_b = session_data.get("twin_b", {}) or {}
    name_a = twin_a.get("display_name", "Twin A") if isinstance(twin_a, dict) else "Twin A"
    name_b = twin_b.get("display_name", "Twin B") if isinstance(twin_b, dict) else "Twin B"
    color_a = twin_a.get("color", "#C084FC") if isinstance(twin_a, dict) else "#C084FC"
    color_b = twin_b.get("color", "#F59E0B") if isinstance(twin_b, dict) else "#F59E0B"

    messages_html = []
    messages = session_data.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        msg_type = msg.get("type", "")
        sender = _html_escape(str(msg.get("sender", "")))
        content = _html_escape(str(msg.get("content", "")))

        if msg_type == "twin":
            color = color_a if msg.get("twin_role") == "twin_a" else color_b
            align = "left" if msg.get("twin_role") == "twin_a" else "right"
            border_side = "border-left" if align == "left" else "border-right"
            text_align = f"text-align:{align};"
            messages_html.append(
                f'<div class="message" style="{border_side}:3px solid {color};{text_align}">'
                f'<div class="sender" style="color:{color}">{sender}</div>'
                f'<div class="content">{content}</div></div>'
            )
        elif msg_type == "thought":
            target_name = _html_escape(
                str(msg.get("metadata", {}).get("target_name", "?"))
            )
            messages_html.append(
                f'<div class="thought">💭 <em>[Thought → {target_name}]</em> {content}</div>'
            )
        elif msg_type == "third_agent":
            messages_html.append(
                f'<div class="message" style="border-left:3px solid #34D399;">'
                f'<div class="sender" style="color:#34D399">🎭 {sender}</div>'
                f'<div class="content">{content}</div></div>'
            )

    body = "\n".join(messages_html)
    session_id = _html_escape(str(session_data.get("id", "")))
    turn_count = session_data.get("turn_count", 0)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name_a} × {name_b} — Doppelchatter</title>
<style>
body {{ background:#0f0f0f; color:#e0e0e0; font-family:Georgia,serif;
       max-width:700px; margin:40px auto; padding:0 20px; line-height:1.6; }}
h1 {{ color:#e0e0e0; font-size:1.5em; border-bottom:1px solid #2a2a2a; padding-bottom:12px; }}
.meta {{ color:#888; font-size:0.85em; margin-bottom:24px; }}
.message {{ padding:8px 12px; margin-bottom:8px; border-radius:6px; }}
.sender {{ font-weight:bold; font-size:0.85em; margin-bottom:2px; }}
.content {{ font-size:1em; }}
.thought {{ color:#818CF8; font-style:italic; font-size:0.9em;
            padding:6px 12px; margin:8px 0; }}
.footer {{ color:#555; font-size:0.8em; margin-top:32px; text-align:center;
           border-top:1px solid #2a2a2a; padding-top:12px; }}
</style>
</head>
<body>
<h1>{_html_escape(name_a)} × {_html_escape(name_b)}</h1>
<div class="meta">Session: {session_id} · Turns: {turn_count}</div>
{body}
<div class="footer">— fin —<br>Exported from Doppelchatter</div>
</body>
</html>"""


def _html_escape(text: str) -> str:
    """Minimal HTML escaping."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
