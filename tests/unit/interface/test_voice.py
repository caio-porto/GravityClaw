import pytest
from unittest.mock import patch, mock_open, MagicMock
import os
import requests
from src.interface.voice import VoiceProcessor

@pytest.fixture
def voice_processor():
    with patch.dict(os.environ, {"GROQ_API_KEY": "test_api_key"}):
        return VoiceProcessor()

def test_transcribe_audio_missing_api_key():
    with patch.dict(os.environ, {}, clear=True):
        processor = VoiceProcessor()
        with pytest.raises(ValueError, match="GROQ_API_KEY is not set."):
            processor.transcribe_audio("test.ogg")

@patch("src.interface.voice.requests.post")
@patch("builtins.open", new_callable=mock_open, read_data=b"dummy audio data")
def test_transcribe_audio_success(mock_file, mock_post, voice_processor):
    # Setup mock response
    mock_response = MagicMock()
    mock_response.json.return_value = {"text": "This is a test transcription."}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    # Call method
    result = voice_processor.transcribe_audio("test.ogg")

    # Assertions
    assert result == "This is a test transcription."
    mock_post.assert_called_once()

    # Check headers
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test_api_key"

    # Check data
    assert call_kwargs["data"]["model"] == "whisper-large-v3"
    assert call_kwargs["data"]["response_format"] == "json"

@patch("src.interface.voice.requests.post")
@patch("builtins.open", new_callable=mock_open, read_data=b"dummy audio data")
def test_transcribe_audio_api_error(mock_file, mock_post, voice_processor):
    # Setup mock response for error
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Client Error")
    mock_post.return_value = mock_response

    # Call method and expect error
    with pytest.raises(requests.exceptions.HTTPError):
        voice_processor.transcribe_audio("test.ogg")
