from unittest.mock import patch, MagicMock

# Mock problematic module to prevent import error
patch.dict("sys.modules", {"src.memory": MagicMock(), "src.memory.core": MagicMock(), "src.memory.buffer": MagicMock()}).start()

from fastapi.testclient import TestClient
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

@patch("src.api.server.os.path.exists")
@patch("builtins.open")
def test_get_core_memory_error(mock_open, mock_exists):
    mock_exists.return_value = True
    mock_open.side_effect = Exception("Failed to open file")
    response = client.get("/api/memory/core")
    assert response.status_code == 500
    assert response.json() == {"error": "Failed to open file"}
