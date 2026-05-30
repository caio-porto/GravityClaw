from fastapi.testclient import TestClient
from unittest.mock import patch

from src.api.server import app

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
