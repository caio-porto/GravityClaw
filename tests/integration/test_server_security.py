import pytest
from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app)

def test_delete_skill_path_traversal():
    """Test that delete_skill rejects path traversal payloads."""
    # fastapi strips trailing slashes and resolves '..' in URL parsing
    response = client.delete("/api/skills/invalid_skill$name")
    assert response.status_code == 400
    assert response.json() == {"error": "Invalid 'skill_id'"}

def test_get_skill_path_traversal():
    """Test that get_skill rejects path traversal payloads."""
    response = client.get("/api/skills/..%5C")
    assert response.status_code == 400
    assert response.json() == {"error": "Invalid 'skill_id'"}

def test_save_skill_path_traversal():
    """Test that save_skill rejects path traversal payloads."""
    response = client.put("/api/skills/..%5Cinvalid", json={"content": "test"})
    assert response.status_code == 400
    assert response.json() == {"error": "Invalid 'skill_id'"}

def test_install_catalog_skill_path_traversal():
    """Test that install_catalog_skill rejects path traversal payloads."""
    response = client.post("/api/skills/catalog/install", json={"skill_id": "../invalid"})
    assert response.status_code == 400
    assert response.json() == {"error": "Invalid 'skill_id'"}
