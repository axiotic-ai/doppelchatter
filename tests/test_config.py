"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from doppelchatter.config import (
    load_config,
    load_profiles,
    load_scenarios,
)


class TestLoadConfig:
    def test_defaults_without_file(self, tmp_path: Path) -> None:
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.server.port == 8420
        assert config.server.host == "127.0.0.1"
        assert config.llm.temperature == 0.85
        assert config.llm.max_tokens == 512
        assert config.engine.first_speaker == "twin_a"
        assert config.engine.max_turns == 0

    def test_load_from_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump({
            "server": {"port": 9000, "host": "0.0.0.0"},
            "llm": {"temperature": 0.5, "max_tokens": 256},
            "engine": {
                "first_speaker": "twin_b",
                "max_turns": 10,
                "turn_delay": {"mode": "fixed", "min_seconds": 2.0},
            },
        }))
        config = load_config(config_file)
        assert config.server.port == 9000
        assert config.server.host == "0.0.0.0"
        assert config.llm.temperature == 0.5
        assert config.llm.max_tokens == 256
        assert config.engine.first_speaker == "twin_b"
        assert config.engine.max_turns == 10
        assert config.engine.turn_delay.mode == "fixed"

    def test_env_overrides(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOPPEL_PORT", "9999")
        monkeypatch.setenv("DOPPEL_HOST", "0.0.0.0")
        monkeypatch.setenv("DOPPEL_MODEL", "test/model")
        monkeypatch.setenv("DOPPEL_API_KEY", "sk-test")
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.server.port == 9999
        assert config.server.host == "0.0.0.0"
        assert config.llm.default_model == "test/model"
        assert config.llm.api_key == "sk-test"

    def test_api_key_fallback(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fallback")
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.llm.api_key == "sk-fallback"

    def test_api_key_priority(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DOPPEL_API_KEY", "sk-primary")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fallback")
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.llm.api_key == "sk-primary"

    def test_turn_delay_random(self, tmp_path: Path) -> None:
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.engine.turn_delay.mode == "random"
        assert config.engine.turn_delay.min_seconds == 1.5
        assert config.engine.turn_delay.max_seconds == 4.0

    def test_empty_yaml_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        config = load_config(config_file)
        assert config.server.port == 8420


class TestLoadProfiles:
    def test_load_valid_profiles(self, tmp_path: Path) -> None:
        profile = {"name": "Test", "system_prompt": "Be test."}
        (tmp_path / "test.yaml").write_text(yaml.dump(profile))
        profiles = load_profiles(tmp_path)
        assert "test" in profiles
        assert profiles["test"].name == "Test"

    def test_skip_invalid_profile(self, tmp_path: Path) -> None:
        (tmp_path / "bad.yaml").write_text("not_a_dict")
        profiles = load_profiles(tmp_path)
        assert len(profiles) == 0

    def test_skip_missing_required(self, tmp_path: Path) -> None:
        (tmp_path / "incomplete.yaml").write_text(yaml.dump({"name": "Nosy"}))
        profiles = load_profiles(tmp_path)
        assert len(profiles) == 0

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        profiles = load_profiles(tmp_path / "nope")
        assert len(profiles) == 0

    def test_load_yml_extension(self, tmp_path: Path) -> None:
        profile = {"name": "YmlTest", "system_prompt": "Be yml."}
        (tmp_path / "ymltest.yml").write_text(yaml.dump(profile))
        profiles = load_profiles(tmp_path)
        assert "ymltest" in profiles

    def test_multiple_profiles(self, tmp_path: Path) -> None:
        for name in ["alice", "bob", "charlie"]:
            profile = {"name": name.title(), "system_prompt": f"Be {name}."}
            (tmp_path / f"{name}.yaml").write_text(yaml.dump(profile))
        profiles = load_profiles(tmp_path)
        assert len(profiles) == 3


class TestLoadScenarios:
    def test_load_valid_scenario(self, tmp_path: Path) -> None:
        scenario = {
            "name": "Late Night",
            "twins": {"a": "shannon", "b": "antreas"},
        }
        (tmp_path / "late-night.yaml").write_text(yaml.dump(scenario))
        scenarios = load_scenarios(tmp_path)
        assert "late-night" in scenarios
        assert scenarios["late-night"]["name"] == "Late Night"

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        scenarios = load_scenarios(tmp_path / "nope")
        assert len(scenarios) == 0

    def test_skip_invalid_scenario(self, tmp_path: Path) -> None:
        (tmp_path / "bad.yaml").write_text("not_a_dict")
        scenarios = load_scenarios(tmp_path)
        assert len(scenarios) == 0
