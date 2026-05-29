import pytest
import yaml
from unittest.mock import patch
from src.agent.loop import ModelManager

@pytest.fixture
def mock_config(tmp_path):
    config = {
        "models": {
            "primary": {"provider": "antigravity", "url": "http://localhost:3000"},
            "fallback": [
                {"provider": "groq", "model_name": "llama3-70b"}
            ]
        }
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config, f)
    return str(config_file)

def test_model_manager_fallback(mock_config):
    """Test that if the primary model throws an exception, it falls back to the secondary."""
    manager = ModelManager(config_path=mock_config)

    with patch.object(manager, '_query_antigravity') as mock_primary:
        # Force primary to fail
        mock_primary.side_effect = Exception("Rate limit exceeded")

        with patch.object(manager, '_query_fallback') as mock_fallback:
            mock_fallback.return_value = "Response from fallback."

            result = manager.query("Test prompt")
            
            # Ensure primary was called and failed
            mock_primary.assert_called_once_with("Test prompt")
            
            # Ensure fallback was subsequently called
            mock_fallback.assert_called_once_with("Test prompt")
            
            # Ensure result comes from fallback
            assert result == "Response from fallback."
