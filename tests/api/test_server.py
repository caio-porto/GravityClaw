import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, mock_open

from src.api.server import app, verify_credentials

@pytest.fixture(autouse=True)
def setup_overrides():
    app.dependency_overrides[verify_credentials] = lambda: None

client = TestClient(app)

@patch("src.api.server._load_config")
@patch("src.api.server.os.environ.get")
def test_get_config_success(mock_env_get, mock_load_config):
    mock_env_get.side_effect = lambda k: "admin" if k == "API_USERNAME" else "secret" if k == "API_PASSWORD" else None
    mock_load_config.return_value = {"key": "value"}
    response = client.get("/api/config", auth=("admin", "secret"))
    assert response.status_code == 200
    assert response.json() == {"key": "value"}

@patch("src.api.server._load_config")
@patch("src.api.server.os.environ.get")
def test_get_config_error(mock_env_get, mock_load_config):
    mock_env_get.side_effect = lambda k: "admin" if k == "API_USERNAME" else "secret" if k == "API_PASSWORD" else None
    mock_load_config.side_effect = Exception("Failed to load config")
    response = client.get("/api/config", auth=("admin", "secret"))
    assert response.status_code == 500
    assert response.json() == {"error": "Failed to load config"}

@patch("src.api.server.bot_task")
@patch("os.environ.get")
@patch("src.api.server._load_env_keys")
@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open, read_data='{"mcpServers": {"test-mcp": {"command": "npx", "args": ["test"], "env": {"VAR": "val"}}}}')
def test_get_integrations_success(mock_file, mock_exists, mock_load_env_keys, mock_env_get, mock_bot_task):
    mock_exists.return_value = True

    mock_load_env_keys.return_value = [
        {"name": "TELEGRAM_BOT_TOKEN", "is_set": True, "is_custom": False}
    ]

    def side_effect(key, default=None):
        if key == "TELEGRAM_BOT_USERNAME":
            return "TestBot"
        elif key == "TELEGRAM_BOT_TOKEN":
            return "12345:ABC"
        return default

    mock_env_get.side_effect = side_effect

    # Mock bot_task running
    mock_bot_task.done.return_value = False

    response = client.get("/api/integrations")
    assert response.status_code == 200

    data = response.json()
    assert data["telegram"]["status"] == "running"
    assert data["telegram"]["bot_running"] is True
    assert data["telegram"]["bot_name"] == "TestBot"
    assert data["telegram"]["token_configured"] is True

    assert len(data["mcp_tools"]) == 1
    assert data["mcp_tools"][0]["name"] == "test-mcp"
    assert data["mcp_tools"][0]["command"] == "npx"
    assert data["mcp_tools"][0]["args"] == ["test"]
    assert data["mcp_tools"][0]["env"] == {"VAR": "val"}

    assert data["env_keys"] == [{"name": "TELEGRAM_BOT_TOKEN", "is_set": True, "is_custom": False}]


@patch("src.api.server.bot_task", None)
@patch("os.environ.get")
@patch("src.api.server._load_env_keys")
@patch("os.path.exists")
def test_get_integrations_no_mcp_and_no_bot(mock_exists, mock_load_env_keys, mock_env_get):
    mock_exists.return_value = False

    mock_load_env_keys.return_value = []

    def side_effect(key, default=None):
        if key == "TELEGRAM_BOT_USERNAME":
            return default
        if key == "TELEGRAM_BOT_TOKEN":
            return ""
        return default

    mock_env_get.side_effect = side_effect

    response = client.get("/api/integrations")
    assert response.status_code == 200

    data = response.json()
    assert data["telegram"]["status"] == "stopped"
    assert data["telegram"]["bot_running"] is False
    assert data["telegram"]["bot_name"] == "GravityClawBot"
    assert data["telegram"]["token_configured"] is False

    assert data["mcp_tools"] == []
    assert data["env_keys"] == []
