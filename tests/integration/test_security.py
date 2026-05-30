import pytest
import requests

# We can test by sending requests directly if the server is up,
# or use TestClient with mocked dependencies.
# Given that the server relies on many submodules that might be missing in this environment,
# let's mock the modules.
import sys
from unittest.mock import MagicMock, patch

# Mock src.memory before importing app
# 1. Save original modules to prevent test pollution
_orig_modules = {
    'src.memory': sys.modules.get('src.memory'),
    'src.memory.core': sys.modules.get('src.memory.core'),
    'src.memory.buffer': sys.modules.get('src.memory.buffer'),
    'src.memory.core.CoreMemory': sys.modules.get('src.memory.core.CoreMemory'),
    'src.memory.buffer.DailyBuffer': sys.modules.get('src.memory.buffer.DailyBuffer'),
}

# 2. Temporarily inject mocks for the duration of the imports
sys.modules['src.memory'] = MagicMock()
sys.modules['src.memory.core'] = MagicMock()
sys.modules['src.memory.buffer'] = MagicMock()
sys.modules['src.memory.core.CoreMemory'] = MagicMock()
sys.modules['src.memory.buffer.DailyBuffer'] = MagicMock()

try:
    from fastapi.testclient import TestClient
    from src.api.server import app
finally:
    # 3. Restore original modules immediately to preserve test isolation
    for name, orig in _orig_modules.items():
        if orig is not None:
            sys.modules[name] = orig
        else:
            sys.modules.pop(name, None)
import os

client = TestClient(app)

def test_get_daily_memory_path_traversal():
    # Attempt a path traversal attack
    with patch("src.api.server.os.environ.get") as mock_env_get:
        mock_env_get.side_effect = lambda k: "admin" if k == "API_USERNAME" else "secret" if k == "API_PASSWORD" else None
        response = client.get("/api/memory/daily?date=../../../etc/passwd", auth=("admin", "secret"))
        assert response.status_code == 400
        assert response.json()["error"] == "Invalid date format. Expected YYYY-MM-DD."

def test_get_daily_memory_valid_date():
    # A valid date format but the file may not exist
    with patch("src.api.server.os.environ.get") as mock_env_get:
        mock_env_get.side_effect = lambda k: "admin" if k == "API_USERNAME" else "secret" if k == "API_PASSWORD" else None
        response = client.get("/api/memory/daily?date=2024-01-01", auth=("admin", "secret"))
        assert response.status_code == 404
        assert "No daily log found for" in response.json()["error"]
