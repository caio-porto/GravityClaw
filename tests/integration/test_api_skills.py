import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys

# Mock src.memory before importing app, since the module is dynamically loaded or missing
class MockCoreMemory:
    def get_context(self):
        return ""

class MockDailyBuffer:
    def get_recent_context(self, lines=80, max_days=3):
        return ""
    def add_interaction(self, user_id, input, response):
        pass

mock_memory = MagicMock()
mock_memory.core.CoreMemory = MockCoreMemory
mock_memory.buffer.DailyBuffer = MockDailyBuffer

sys.modules['src.memory'] = mock_memory
sys.modules['src.memory.core'] = mock_memory.core
sys.modules['src.memory.buffer'] = mock_memory.buffer

from src.api.server import app
import src.api.server as server

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_cache():
    """Reset the global cache before each test."""
    original = server._catalog_cache
    server._catalog_cache = None
    yield
    server._catalog_cache = original

@patch('hashlib.sha256')
def test_get_skills_catalog_success(mock_sha256):
    """Test successful fetching of skills catalog."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"fake content"
    mock_response.json.return_value = {"skills": [{"name": "test_skill"}]}

    mock_hash = MagicMock()
    mock_hash.hexdigest.return_value = "c36c9f56d96427eeb91b10318865a3e9cab9671f2eb172d93e9d2fdeeb83ac9d"
    mock_sha256.return_value = mock_hash

    with patch('requests.get', return_value=mock_response):
        response = client.get("/api/skills/catalog")

    assert response.status_code == 200
    assert response.json() == {"skills": [{"name": "test_skill"}]}

def test_get_skills_catalog_non_200_status():
    """Test fetching skills catalog when the server returns a non-200 status."""
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch('requests.get', return_value=mock_response):
        response = client.get("/api/skills/catalog")

    assert response.status_code == 500
    assert response.json() == {"error": "Failed to fetch catalog: HTTP 404"}

def test_get_skills_catalog_exception():
    """Test fetching skills catalog when requests.get raises an exception."""
    with patch('requests.get', side_effect=Exception("Network error")):
        response = client.get("/api/skills/catalog")

    assert response.status_code == 500
    assert response.json() == {"error": "Network error"}
