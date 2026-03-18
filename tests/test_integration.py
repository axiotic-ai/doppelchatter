"""Integration tests — FastAPI app with mock LLM."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doppelchatter.app import create_app
from doppelchatter.config import AppConfig, EngineConfig, LLMConfig, ServerConfig, TurnDelayConfig


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    """Config pointing to temp directories with real profile files."""
    twins_dir = tmp_path / "twins"
    twins_dir.mkdir()
    (twins_dir / "alice.yaml").write_text(
        "name: Alice\nsystem_prompt: You are Alice. Be brief.\navatar: '🌙'\ncolor: '#C084FC'\n"
    )
    (twins_dir / "bob.yaml").write_text(
        "name: Bob\nsystem_prompt: You are Bob. Be brief.\navatar: '🔬'\ncolor: '#F59E0B'\n"
    )

    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "test.yaml").write_text(
        "name: Test Scenario\ndescription: A test scenario.\ntwins:\n  a: alice\n  b: bob\n"
    )

    return AppConfig(
        server=ServerConfig(),
        llm=LLMConfig(api_key="test-key"),
        engine=EngineConfig(
            turn_delay=TurnDelayConfig(mode="fixed", min_seconds=0.0, max_seconds=0.0),
            max_turns=3,
        ),
        twins_dir=str(twins_dir),
        scenarios_dir=str(scenarios_dir),
        sessions_dir=str(tmp_path / "sessions"),
    )


@pytest.fixture
def client(app_config: AppConfig):
    app = create_app(app_config)
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health(self, client: TestClient) -> None:
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_no_session(self, client: TestClient) -> None:
        data = client.get("/api/v1/health").json()
        assert data["active_session"] is None


class TestProfilesEndpoint:
    def test_list_profiles(self, client: TestClient) -> None:
        resp = client.get("/api/v1/profiles")
        assert resp.status_code == 200
        profiles = resp.json()
        assert len(profiles) == 2
        slugs = [p["slug"] for p in profiles]
        assert "alice" in slugs
        assert "bob" in slugs

    def test_get_profile_detail(self, client: TestClient) -> None:
        resp = client.get("/api/v1/profiles/alice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Alice"

    def test_get_profile_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/profiles/nonexistent")
        assert resp.status_code == 404


class TestScenariosEndpoint:
    def test_list_scenarios(self, client: TestClient) -> None:
        resp = client.get("/api/v1/scenarios")
        assert resp.status_code == 200
        scenarios = resp.json()
        assert len(scenarios) == 1
        assert scenarios[0]["name"] == "Test Scenario"


class TestSessionsEndpoint:
    def test_list_sessions_empty(self, client: TestClient) -> None:
        resp = client.get("/api/v1/sessions")
        assert resp.status_code == 200
        assert resp.json() == []


class TestExportEndpoint:
    def test_export_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/sessions/nonexistent/export")
        assert resp.status_code == 404


class TestFrontend:
    def test_serves_html(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Doppelchatter" in resp.text


class TestWebSocketConnection:
    def test_websocket_connect_and_receive_state(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert "profiles" in data
            assert "scenarios" in data
            assert data["server_version"] is not None

    def test_websocket_ping_pong(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # connected event
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_websocket_invalid_json(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # connected
            ws.send_text("not json")
            data = ws.receive_json()
            assert data["type"] == "error"

    def test_websocket_start_session_bad_profile(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # connected
            ws.send_json({
                "type": "start_session",
                "twin_a": "nonexistent",
                "twin_b": "also_nonexistent",
            })
            data = ws.receive_json()
            assert data["type"] == "error"
