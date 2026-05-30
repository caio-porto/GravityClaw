import pytest
import sys
from unittest.mock import MagicMock, patch

# Mock src.memory before importing app
sys.modules['src.memory'] = MagicMock()
sys.modules['src.memory.core'] = MagicMock()
sys.modules['src.memory.buffer'] = MagicMock()
sys.modules['src.memory.core.CoreMemory'] = MagicMock()
sys.modules['src.memory.buffer.DailyBuffer'] = MagicMock()

from fastapi.testclient import TestClient
from src.api.server import app
import os

@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides.clear()

client = TestClient(app)

def test_auth_denied_if_no_env_vars():
    # Ensure variables are unset
    with patch("src.api.server.os.environ.get") as mock_env_get:
        mock_env_get.side_effect = lambda k: None

        response = client.get("/api/config")
        assert response.status_code == 401

        # Try with credentials when none configured
        response = client.get("/api/config", auth=("admin", "secret"))
        assert response.status_code == 401

def test_auth_enforced_if_env_vars_set():
    with patch("src.api.server.os.environ.get") as mock_env_get:
        mock_env_get.side_effect = lambda k: "admin" if k == "API_USERNAME" else "secret" if k == "API_PASSWORD" else None

        response = client.get("/api/config")
        assert response.status_code == 401

        response = client.get("/api/config", auth=("admin", "secret"))
        assert response.status_code == 200

def test_auth_enforced_if_only_password_set():
    with patch("src.api.server.os.environ.get") as mock_env_get:
        mock_env_get.side_effect = lambda k: "secret" if k == "API_PASSWORD" else None

        response = client.get("/api/config")
        assert response.status_code == 401
