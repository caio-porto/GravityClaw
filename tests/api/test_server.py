import sys
from unittest.mock import patch, mock_open, MagicMock, AsyncMock
import asyncio
import pytest

# 1. Save original modules to prevent test pollution
_orig_modules = {
    'src.memory': sys.modules.get('src.memory'),
    'src.memory.core': sys.modules.get('src.memory.core'),
    'src.memory.buffer': sys.modules.get('src.memory.buffer'),
    'src.memory.core.CoreMemory': sys.modules.get('src.memory.core.CoreMemory'),
    'src.memory.buffer.DailyBuffer': sys.modules.get('src.memory.buffer.DailyBuffer'),
}

# 2. Temporarily mock src.memory for importing the server app
sys.modules['src.memory'] = MagicMock()
sys.modules['src.memory.core'] = MagicMock()
sys.modules['src.memory.buffer'] = MagicMock()
sys.modules['src.memory.core.CoreMemory'] = MagicMock()
sys.modules['src.memory.buffer.DailyBuffer'] = MagicMock()

try:
    from fastapi.testclient import TestClient
    from src.api.server import app, verify_credentials
    import src.api.server as server
finally:
    # 3. Restore original modules immediately to preserve test isolation
    for name, orig in _orig_modules.items():
        if orig is not None:
            sys.modules[name] = orig
        else:
            sys.modules.pop(name, None)

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

def test_toggle_telegram_bot_invalid_json():
    response = client.post("/api/integrations/telegram/toggle", content="not json")
    assert response.status_code == 400
    assert response.json() == {"error": "Invalid JSON body"}

@patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": ""})
def test_toggle_telegram_bot_enable_missing_token():
    response = client.post("/api/integrations/telegram/toggle", json={"enabled": True})
    assert response.status_code == 400
    assert response.json() == {"error": "Cannot start bot: TELEGRAM_BOT_TOKEN is missing"}

@patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "some_token"})
@patch("src.api.server.bot_task", None)
@patch("src.api.server.asyncio.create_task")
def test_toggle_telegram_bot_enable_success(mock_create_task):
    mock_task = MagicMock()
    mock_task.done.return_value = False
    mock_create_task.return_value = mock_task

    with patch("src.api.server.telegram_bot_runner", new_callable=MagicMock) as mock_runner:
        response = client.post("/api/integrations/telegram/toggle", json={"enabled": True})

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Telegram Bot started"}
    mock_create_task.assert_called_once()
    assert server.stop_event.is_set() is False

@patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "some_token"})
@patch("src.api.server.asyncio.create_task")
def test_toggle_telegram_bot_enable_already_running(mock_create_task):
    mock_task = MagicMock()
    mock_task.done.return_value = False

    with patch("src.api.server.bot_task", mock_task):
        response = client.post("/api/integrations/telegram/toggle", json={"enabled": True})

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Telegram Bot is already running"}
    mock_create_task.assert_not_called()

def test_toggle_telegram_bot_disable_success():
    mock_task = MagicMock()
    mock_task.done.return_value = False

    with patch("src.api.server.bot_task", mock_task):
        with patch("src.api.server.asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            response = client.post("/api/integrations/telegram/toggle", json={"enabled": False})

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Telegram Bot stopped"}
    assert server.stop_event.is_set() is True
    assert server.bot_task is None

def test_toggle_telegram_bot_disable_timeout():
    mock_task = MagicMock()
    mock_task.done.return_value = False

    with patch("src.api.server.bot_task", mock_task):
        with patch("src.api.server.asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            mock_wait.side_effect = asyncio.TimeoutError()
            response = client.post("/api/integrations/telegram/toggle", json={"enabled": False})

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Telegram Bot stopped"}
    assert server.stop_event.is_set() is True
    mock_task.cancel.assert_called_once()
    assert server.bot_task is None

def test_toggle_telegram_bot_disable_already_stopped():
    with patch("src.api.server.bot_task", None):
        response = client.post("/api/integrations/telegram/toggle", json={"enabled": False})

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Telegram Bot is already stopped"}
