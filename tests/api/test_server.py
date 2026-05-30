from fastapi.testclient import TestClient
from unittest.mock import patch

from src.api.server import app

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

from unittest.mock import mock_open, patch, MagicMock

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
@patch("builtins.open", new_callable=mock_open, read_data="Core memory content")
def test_get_core_memory_exists(mock_file, mock_exists):
    response = client.get("/api/memory/core")
    assert response.status_code == 200
    assert response.json() == {"content": "Core memory content"}

@patch("os.path.exists", return_value=False)
def test_get_core_memory_not_exists(mock_exists):
    response = client.get("/api/memory/core")
    assert response.status_code == 200
    assert response.json() == {"content": ""}

@patch("builtins.open", new_callable=mock_open)
def test_update_core_memory_success(mock_file):
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
@patch("builtins.open", new_callable=mock_open, read_data="Daily log content")
def test_get_daily_memory_exists(mock_file, mock_exists):
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
        with patch("builtins.open", new_callable=mock_open, read_data="---\nname: Test Skill\ndescription: A test skill\n---\ncontent"):
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
    # and the server instance might persist, let's force the cache to None.
    import src.api.server
    src.api.server._catalog_cache = None

    response = client.get("/api/skills/catalog")
    assert response.status_code == 200
    assert response.json() == [{"id": "remote-skill"}]

@patch("requests.get")
@patch("os.makedirs")
@patch("builtins.open", new_callable=mock_open)
def test_install_catalog_skill(mock_file, mock_makedirs, mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "skill content"
    mock_get.return_value = mock_response

    response = client.post("/api/skills/catalog/install", json={"skill_id": "new-skill"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"

@patch("os.path.exists", return_value=True)
@patch("builtins.open", new_callable=mock_open, read_data="skill content")
def test_get_skill(mock_file, mock_exists):
    response = client.get("/api/skills/test-skill")
    assert response.status_code == 200
    assert response.json() == {"id": "test-skill", "content": "skill content"}

@patch("os.makedirs")
@patch("builtins.open", new_callable=mock_open)
def test_save_skill(mock_file, mock_makedirs):
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
