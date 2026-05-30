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

@patch("builtins.open", new_callable=mock_open, read_data="<html>UI</html>")
def test_serve_ui_success(mock_file):
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "<html>UI</html>"

@patch("builtins.open", side_effect=FileNotFoundError)
def test_serve_ui_not_found(mock_file):
    response = client.get("/")
    assert response.status_code == 404
    assert "UI not found" in response.text

@patch("src.api.server._load_config")
def test_get_status(mock_load_config):
    mock_load_config.return_value = {
        "models": {
            "primary": {
                "provider": "test_provider",
                "model_name": "test_model"
            }
        }
    }
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "uptime_seconds" in data
    assert data["model_provider"] == "test_provider"
    assert data["model_name"] == "test_model"

def test_post_chat_empty_message():
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 400
    assert response.json() == {"error": "Message cannot be empty"}

def test_post_chat_invalid_json():
    response = client.post("/api/chat", data="not a json")
    assert response.status_code == 400
    assert response.json() == {"error": "Invalid JSON body"}

@patch("src.api.server.agent.process_input")
def test_post_chat_success(mock_process_input):
    mock_process_input.return_value = "Hello from agent"
    response = client.post("/api/chat", json={"message": "Hi"})
    assert response.status_code == 200
    assert response.json() == {"response": "Hello from agent"}

def test_get_chat_history():
    response = client.get("/api/chat/history")
    assert response.status_code == 200
    assert "messages" in response.json()

def test_get_logs():
    response = client.get("/api/logs")
    assert response.status_code == 200
    assert "logs" in response.json()

@patch("os.path.exists", return_value=True)
@patch("src.api.server.aiofiles.open")
def test_get_core_memory_exists(mock_aio_open, mock_exists):
    mock_file = AsyncMock()
    mock_file.read.return_value = "Core memory content"
    mock_aio_open.return_value.__aenter__.return_value = mock_file

    response = client.get("/api/memory/core")
    assert response.status_code == 200
    assert response.json() == {"content": "Core memory content"}

@patch("os.path.exists", return_value=False)
def test_get_core_memory_not_exists(mock_exists):
    response = client.get("/api/memory/core")
    assert response.status_code == 200
    assert response.json() == {"content": ""}

@patch("src.api.server.aiofiles.open")
def test_update_core_memory_success(mock_aio_open):
    mock_file = AsyncMock()
    mock_aio_open.return_value.__aenter__.return_value = mock_file

    response = client.put("/api/memory/core", json={"content": "New memory"})
    assert response.status_code == 200
    assert response.json() == {"status": "success"}

def test_update_core_memory_missing_content():
    response = client.put("/api/memory/core", json={})
    assert response.status_code == 400
    assert response.json() == {"error": "Missing 'content' field"}

@patch("glob.glob", return_value=["memory/2023-10-27.md", "memory/2023-10-26.md"])
def test_get_daily_dates(mock_glob):
    response = client.get("/api/memory/daily/dates")
    assert response.status_code == 200
    assert response.json() == {"dates": ["2023-10-27", "2023-10-26"]}

@patch("os.path.exists", return_value=True)
@patch("src.api.server.aiofiles.open")
def test_get_daily_memory_exists(mock_aio_open, mock_exists):
    mock_file = AsyncMock()
    mock_file.read.return_value = "Daily log content"
    mock_aio_open.return_value.__aenter__.return_value = mock_file

    response = client.get("/api/memory/daily?date=2023-10-27")
    assert response.status_code == 200
    assert response.json() == {"date": "2023-10-27", "content": "Daily log content"}

def test_get_daily_memory_missing_date():
    response = client.get("/api/memory/daily")
    assert response.status_code == 400
    assert "Query parameter 'date' is required" in response.json()["error"]

def test_get_daily_memory_invalid_date():
    response = client.get("/api/memory/daily?date=invalid-date")
    assert response.status_code == 400
    assert "Invalid date format" in response.json()["error"]

@patch("os.path.exists", return_value=False)
def test_get_daily_memory_not_exists(mock_exists):
    response = client.get("/api/memory/daily?date=2023-10-27")
    assert response.status_code == 404
    assert "No daily log found" in response.json()["error"]

@patch("os.path.exists", return_value=True)
@patch("builtins.open", new_callable=mock_open, read_data="yaml: content")
def test_get_config_raw_success(mock_file, mock_exists):
    response = client.get("/api/config/raw")
    assert response.status_code == 200
    assert response.json() == {"yaml": "yaml: content"}

@patch("builtins.open", new_callable=mock_open)
def test_update_config_raw_success(mock_file):
    response = client.post("/api/config/raw", json={"yaml": "key: value\n"})
    assert response.status_code == 200
    assert response.json() == {"status": "success"}

def test_update_config_raw_missing_yaml():
    response = client.post("/api/config/raw", json={})
    assert response.status_code == 400
    assert response.json() == {"error": "Missing 'yaml' field"}

def test_update_config_raw_invalid_yaml():
    response = client.post("/api/config/raw", json={"yaml": "invalid: yaml:\n- :"})
    assert response.status_code == 400
    assert "Invalid YAML" in response.json()["error"]

@patch("src.api.server._set_env_key")
def test_save_env_key_success(mock_set_env_key):
    response = client.post("/api/integrations/env/save", json={"name": "TEST_KEY", "value": "test_value"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    mock_set_env_key.assert_called_once_with("TEST_KEY", "test_value")

def test_save_env_key_missing_name():
    response = client.post("/api/integrations/env/save", json={"value": "test_value"})
    assert response.status_code == 400
    assert "Key name is required" in response.json()["error"]

def test_save_env_key_invalid_name():
    response = client.post("/api/integrations/env/save", json={"name": "TEST-KEY", "value": "test_value"})
    assert response.status_code == 400
    assert "alphanumeric characters and underscores" in response.json()["error"]

@patch("src.api.server._unset_env_key")
def test_delete_env_key_success(mock_unset_env_key):
    response = client.delete("/api/integrations/env/TEST_KEY")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    mock_unset_env_key.assert_called_once_with("TEST_KEY")

def test_delete_env_key_empty_name():
    response = client.delete("/api/integrations/env/ ")
    # FastAPI path parameter parsing might handle space differently, let's just make sure it fails if we bypass it.
    # Actually, space is parsed as a path, let's see.
    assert response.status_code in [400, 404, 422] # FastAPI might reject it as 404 or 422 before our check

@patch("src.api.server._load_env_keys", return_value=[{"name": "TEST_KEY", "is_set": True, "is_custom": True}])
@patch("os.path.exists", return_value=True)
@patch("builtins.open", new_callable=mock_open, read_data='{"mcpServers": {"test_tool": {"command": "test", "args": []}}}')
def test_get_integrations(mock_file, mock_exists, mock_load_env_keys):
    response = client.get("/api/integrations")
    assert response.status_code == 200
    data = response.json()
    assert "telegram" in data
    assert "mcp_tools" in data
    assert len(data["mcp_tools"]) == 1
    assert data["mcp_tools"][0]["name"] == "test_tool"
    assert "env_keys" in data
    assert data["env_keys"][0]["name"] == "TEST_KEY"

@patch("os.path.exists", return_value=False)
@patch("os.makedirs")
@patch("builtins.open", new_callable=mock_open)
def test_save_mcp_server(mock_file, mock_makedirs, mock_exists):
    response = client.post("/api/integrations/mcp/save", json={"name": "new_tool", "command": "python", "args": ["-c", "print('hello')"]})
    assert response.status_code == 200
    assert response.json()["status"] == "success"

def test_save_mcp_server_missing_fields():
    response = client.post("/api/integrations/mcp/save", json={"name": "new_tool"})
    assert response.status_code == 400
    assert "Fields 'name' and 'command' are required" in response.json()["error"]

@patch("os.path.exists", return_value=True)
@patch("builtins.open", new_callable=mock_open, read_data='{"mcpServers": {"test_tool": {"command": "test"}}}')
def test_delete_mcp_server_success(mock_file, mock_exists):
    response = client.delete("/api/integrations/mcp/test_tool")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

@patch("os.path.exists", return_value=True)
@patch("builtins.open", new_callable=mock_open, read_data='{"mcpServers": {}}')
def test_delete_mcp_server_not_found(mock_file, mock_exists):
    response = client.delete("/api/integrations/mcp/test_tool")
    assert response.status_code == 404
    assert "not found" in response.json()["error"]

@patch("src.api.server.SKILLS_DIR", "/tmp/fake_skills_dir")
@patch("os.scandir")
def test_list_skills(mock_scandir):
    # Setup mock scandir
    mock_entry = MagicMock()
    mock_entry.is_dir.return_value = True
    mock_entry.name = "test-skill"
    mock_entry.path = "/tmp/fake_skills_dir/test-skill"

    mock_scandir.return_value = [mock_entry]

    with patch("os.path.exists", return_value=True):
        with patch("src.api.server.aiofiles.open") as mock_aio_open:
            mock_file = AsyncMock()
            mock_file.read.return_value = "---\nname: Test Skill\ndescription: A test skill\n---\ncontent"
            mock_aio_open.return_value.__aenter__.return_value = mock_file
            response = client.get("/api/skills")
            assert response.status_code == 200
            skills = response.json().get("skills", [])
            assert len(skills) == 1
            assert skills[0]["id"] == "test-skill"
            assert skills[0]["name"] == "Test Skill"
            assert skills[0]["description"] == "A test skill"

@patch("requests.get")
def test_get_skills_catalog(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"id": "remote-skill"}]
    mock_get.return_value = mock_response

    # We need to clear the catalog cache first if it exists, but since tests run in arbitrary order
    # and the server instance might persist, let's force the catalog cache to None.
    import src.api.server
    src.api.server._catalog_cache = None

    response = client.get("/api/skills/catalog")
    assert response.status_code == 200
    assert response.json() == [{"id": "remote-skill"}]

@patch("requests.get")
@patch("os.makedirs")
@patch("src.api.server.aiofiles.open")
def test_install_catalog_skill(mock_aio_open, mock_makedirs, mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "skill content"
    mock_get.return_value = mock_response

    mock_file = AsyncMock()
    mock_aio_open.return_value.__aenter__.return_value = mock_file

    response = client.post("/api/skills/catalog/install", json={"skill_id": "new-skill"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"

@patch("os.path.exists", return_value=True)
@patch("src.api.server.aiofiles.open")
def test_get_skill(mock_aio_open, mock_exists):
    mock_file = AsyncMock()
    mock_file.read.return_value = "skill content"
    mock_aio_open.return_value.__aenter__.return_value = mock_file

    response = client.get("/api/skills/test-skill")
    assert response.status_code == 200
    assert response.json() == {"id": "test-skill", "content": "skill content"}

@patch("os.makedirs")
@patch("src.api.server.aiofiles.open")
def test_save_skill(mock_aio_open, mock_makedirs):
    mock_file = AsyncMock()
    mock_aio_open.return_value.__aenter__.return_value = mock_file

    response = client.put("/api/skills/test-skill", json={"content": "new content"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["id"] == "test-skill"

@patch("os.path.exists", return_value=True)
@patch("shutil.rmtree")
def test_delete_skill(mock_rmtree, mock_exists):
    response = client.delete("/api/skills/test-skill")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

def test_get_logs_empty():
    from src.api.server import log_buffer
    log_buffer.clear()

    response = client.get("/api/logs")
    assert response.status_code == 200
    assert response.json() == {"logs": []}


def test_get_logs_with_data():
    from src.api.server import log_buffer
    log_buffer.clear()
    log_buffer.append({"timestamp": "2023-01-01T10:00:00", "level": "INFO", "logger": "test", "message": "msg1"})
    log_buffer.append({"timestamp": "2023-01-01T10:01:00", "level": "ERROR", "logger": "test", "message": "msg2"})
    log_buffer.append({"timestamp": "2023-01-01T10:02:00", "level": "INFO", "logger": "test", "message": "msg3"})

    response = client.get("/api/logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert len(data["logs"]) == 3
    # Logs are sorted by timestamp descending
    assert data["logs"][0]["message"] == "msg3"
    assert data["logs"][2]["message"] == "msg1"


def test_get_logs_with_limit():
    from src.api.server import log_buffer
    log_buffer.clear()
    for i in range(5):
        log_buffer.append({"timestamp": f"2023-01-01T10:0{i}:00", "level": "INFO", "logger": "test", "message": f"msg{i}"})

    response = client.get("/api/logs?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert len(data["logs"]) == 2
    # Should return the most recent entries sorted descending
    assert data["logs"][0]["message"] == "msg4"
    assert data["logs"][1]["message"] == "msg3"


def test_get_logs_with_level_filter():
    from src.api.server import log_buffer
    log_buffer.clear()
    log_buffer.append({"timestamp": "2023-01-01T10:00:00", "level": "INFO", "logger": "test", "message": "msg1"})
    log_buffer.append({"timestamp": "2023-01-01T10:01:00", "level": "ERROR", "logger": "test", "message": "msg2"})
    log_buffer.append({"timestamp": "2023-01-01T10:02:00", "level": "WARNING", "logger": "test", "message": "msg3"})
    log_buffer.append({"timestamp": "2023-01-01T10:03:00", "level": "ERROR", "logger": "test", "message": "msg4"})

    response = client.get("/api/logs?level=error")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert len(data["logs"]) == 2
    # Logs are sorted by timestamp descending
    assert data["logs"][0]["message"] == "msg4"
    assert data["logs"][1]["message"] == "msg2"

@patch("src.api.server.os.path.exists")
@patch("src.api.server.aiofiles.open")
def test_get_core_memory_error(mock_aio_open, mock_exists):
    mock_exists.return_value = True
    mock_aio_open.side_effect = Exception("Failed to open file")
    response = client.get("/api/memory/core")
    assert response.status_code == 500
    assert response.json() == {"error": "Failed to open file"}
