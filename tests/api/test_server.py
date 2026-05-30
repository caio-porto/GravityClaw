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
