import pytest
import requests

# We can test by sending requests directly if the server is up,
# or use TestClient with mocked dependencies.
# Given that the server relies on many submodules that might be missing in this environment,
# let's mock the modules.
import sys
from unittest.mock import MagicMock

# Mock src.memory before importing app
sys.modules['src.memory'] = MagicMock()
sys.modules['src.memory.core'] = MagicMock()
sys.modules['src.memory.buffer'] = MagicMock()
sys.modules['src.memory.core.CoreMemory'] = MagicMock()
sys.modules['src.memory.buffer.DailyBuffer'] = MagicMock()

from fastapi.testclient import TestClient
from src.api.server import app
import os

client = TestClient(app)

def test_get_daily_memory_path_traversal():
    # Attempt a path traversal attack
    response = client.get("/api/memory/daily?date=../../../etc/passwd")
    assert response.status_code == 400
    assert response.json()["error"] == "Invalid date format. Expected YYYY-MM-DD."

def test_get_daily_memory_valid_date():
    # A valid date format but the file may not exist
    response = client.get("/api/memory/daily?date=2024-01-01")
    assert response.status_code == 404
    assert "No daily log found for" in response.json()["error"]
