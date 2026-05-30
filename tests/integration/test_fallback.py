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

from unittest.mock import patch, MagicMock
import requests
import os

def test_query_groq_error_handling(mock_config):
    """Test that _query_groq properly logs and raises HTTP errors."""
    manager = ModelManager(config_path=mock_config)
    messages = [{"role": "user", "content": "Test prompt"}]

    with patch.dict(os.environ, {"GROQ_API_KEY": "test_key"}):
        with patch('src.agent.loop.requests.post') as mock_post:
            # Create a mock response that will raise an HTTPError
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Client Error")
            mock_response.text = '{"error": {"message": "Invalid request"}}'
            mock_post.return_value = mock_response

            with patch('src.agent.loop.logger.error') as mock_logger_error:
                with pytest.raises(requests.exceptions.HTTPError):
                    manager._query_groq(messages, "llama3-70b")

                # Verify logger.error was called with the correct details
                mock_logger_error.assert_called_once_with('Groq Error Details: {"error": {"message": "Invalid request"}}')


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
