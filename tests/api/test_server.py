import sys
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

# Mock src.memory before importing app, just like in test_security.py
sys.modules['src.memory'] = MagicMock()
sys.modules['src.memory.core'] = MagicMock()
sys.modules['src.memory.buffer'] = MagicMock()
sys.modules['src.memory.core.CoreMemory'] = MagicMock()
sys.modules['src.memory.buffer.DailyBuffer'] = MagicMock()

from fastapi.testclient import TestClient
from src.api.server import app
import src.api.server as server

client = TestClient(app)

@patch("src.api.server._load_config")
def test_get_config_success(mock_load_config):
    mock_load_config.return_value = {"key": "value"}
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"key": "value"}

@patch("src.api.server._load_config")
def test_get_config_error(mock_load_config):
    mock_load_config.side_effect = Exception("Failed to load config")
    response = client.get("/api/config")
    assert response.status_code == 500
    assert response.json() == {"error": "Failed to load config"}

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
