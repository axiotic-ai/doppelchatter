"""Configuration loading — YAML + environment variable overrides."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from doppelchatter.models import TwinProfile

logger = logging.getLogger(__name__)


# ─── Config Dataclasses (frozen — immutable after creation) ───────────────────


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8420


@dataclass(frozen=True)
class LLMConfig:
    api_key: str = ""
    anthropic_api_key: str = ""
    default_model: str = "anthropic/claude-sonnet-4-20250514"
    temperature: float = 0.85
    max_tokens: int = 512
    timeout_seconds: float = 120.0
    fallback_models: tuple[str, ...] = (
        "google/gemini-2.5-flash",
        "openai/gpt-4o-mini",
    )


@dataclass(frozen=True)
class TurnDelayConfig:
    mode: str = "random"
    min_seconds: float = 1.5
    max_seconds: float = 4.0


@dataclass(frozen=True)
class EngineConfig:
    turn_delay: TurnDelayConfig = field(default_factory=TurnDelayConfig)
    first_speaker: str = "twin_a"
    max_turns: int = 0
    max_context_messages: int = 50


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    twins_dir: str = "./twins"
    scenarios_dir: str = "./scenarios"
    sessions_dir: str = "./sessions"
    log_level: str = "info"


# ─── Config Loading ──────────────────────────────────────────────────────────


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from YAML + environment variables.

    Priority: env vars > config file > defaults.
    """
    data: dict[str, object] = {}
    path = config_path or Path("doppelchatter.yaml")
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}

    api_key = os.environ.get("DOPPEL_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    server_data = dict(data.get("server", {}) or {})  # type: ignore[arg-type]
    llm_data = dict(data.get("llm", {}) or {})  # type: ignore[arg-type]
    engine_data = dict(data.get("engine", {}) or {})  # type: ignore[arg-type]

    # Environment overrides
    if os.environ.get("DOPPEL_PORT"):
        server_data["port"] = int(os.environ["DOPPEL_PORT"])
    if os.environ.get("DOPPEL_HOST"):
        server_data["host"] = os.environ["DOPPEL_HOST"]
    if os.environ.get("DOPPEL_MODEL"):
        llm_data["default_model"] = os.environ["DOPPEL_MODEL"]
    if os.environ.get("DOPPEL_DEBUG"):
        pass  # Handled at CLI level

    # Build turn delay config
    delay_data = engine_data.pop("turn_delay", {}) or {}
    turn_delay = TurnDelayConfig(**delay_data) if delay_data else TurnDelayConfig()

    # Build fallback models — convert list to tuple for frozen dataclass
    fallback_raw = llm_data.pop("fallback_models", None)
    fallback_models = (
        tuple(fallback_raw) if fallback_raw else LLMConfig.fallback_models
    )

    return AppConfig(
        server=ServerConfig(**server_data),
        llm=LLMConfig(
            api_key=api_key,
            anthropic_api_key=anthropic_api_key,
            fallback_models=fallback_models,
            **{k: v for k, v in llm_data.items() if k not in ("api_key", "anthropic_api_key")},
        ),
        engine=EngineConfig(turn_delay=turn_delay, **engine_data),
        twins_dir=_nested_get(data, "twins", "dir", default="./twins"),
        scenarios_dir=_nested_get(data, "scenarios", "dir", default="./scenarios"),
        sessions_dir=_nested_get(data, "storage", "sessions_dir", default="./sessions"),
        log_level=_nested_get(data, "logging", "level", default="info"),
    )


def _nested_get(data: dict[str, object], *keys: str, default: str = "") -> str:
    """Safely traverse nested dicts."""
    current: object = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return str(current) if current is not None else default


# ─── Profile & Scenario Loading ──────────────────────────────────────────────


def load_profiles(profiles_dir: Path) -> dict[str, TwinProfile]:
    """Load all twin profiles from YAML files.

    Invalid profiles are logged and skipped.
    Returns {slug: TwinProfile} where slug is filename without extension.
    """
    profiles: dict[str, TwinProfile] = {}
    if not profiles_dir.exists():
        logger.warning(f"Profiles directory not found: {profiles_dir}")
        return profiles

    for pattern in ("*.yaml", "*.yml"):
        for path in sorted(profiles_dir.glob(pattern)):
            try:
                with open(path) as f:
                    raw = yaml.safe_load(f)
                if not isinstance(raw, dict):
                    logger.warning(f"Skipping {path.name}: not a YAML mapping")
                    continue
                profile = TwinProfile(**raw)
                profiles[path.stem] = profile
            except Exception as e:
                logger.warning(f"Skipping invalid profile {path.name}: {e}")

    return profiles


def load_scenarios(scenarios_dir: Path) -> dict[str, dict[str, object]]:
    """Load scenario templates. Returns raw dicts."""
    scenarios: dict[str, dict[str, object]] = {}
    if not scenarios_dir.exists():
        return scenarios

    for pattern in ("*.yaml", "*.yml"):
        for path in sorted(scenarios_dir.glob(pattern)):
            try:
                with open(path) as f:
                    raw = yaml.safe_load(f)
                if isinstance(raw, dict):
                    scenarios[path.stem] = raw
            except Exception as e:
                logger.warning(f"Skipping invalid scenario {path.name}: {e}")

    return scenarios
