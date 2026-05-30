import os
import pytest
from unittest.mock import patch, MagicMock, mock_open
import requests
from src.interface.voice import VoiceProcessor, VoiceSynthesizer

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test_groq_api_key")

def test_voice_processor_init_missing_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    processor = VoiceProcessor()
    assert processor.api_key is None
    with pytest.raises(ValueError, match="GROQ_API_KEY is not set."):
        processor.transcribe_audio("dummy.ogg")

@patch("src.interface.voice.requests.post")
@patch("builtins.open", new_callable=mock_open, read_data=b"dummy audio data")
def test_voice_processor_transcribe_audio_success(mock_file, mock_post, mock_env):
    mock_response = MagicMock()
    mock_response.json.return_value = {"text": "Hello, world!"}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    processor = VoiceProcessor()
    result = processor.transcribe_audio("dummy.ogg")

    assert result == "Hello, world!"
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer test_groq_api_key"
    assert "files" in kwargs
    assert "data" in kwargs
    assert kwargs["data"]["model"] == "whisper-large-v3"

@patch("src.interface.voice.requests.post")
@patch("builtins.open", new_callable=mock_open, read_data=b"dummy audio data")
def test_voice_processor_transcribe_audio_http_error(mock_file, mock_post, mock_env):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Bad Request")
    mock_post.return_value = mock_response

    processor = VoiceProcessor()
    with pytest.raises(requests.exceptions.HTTPError):
        processor.transcribe_audio("dummy.ogg")

@patch("src.interface.voice.requests.post")
@patch("builtins.open", new_callable=mock_open)
def test_voice_synthesizer_generate_speech_groq_success(mock_file, mock_post, mock_env):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"fake audio content"
    mock_post.return_value = mock_response

    synthesizer = VoiceSynthesizer()
    success = synthesizer.generate_speech("Test text", "output.opus", speed=1.0)

    assert success is True
    mock_post.assert_called_once()
    mock_file().write.assert_called_once_with(b"fake audio content")

@patch("src.interface.voice.requests.post")
def test_voice_synthesizer_generate_speech_groq_failure_gtts_fallback(mock_post, mock_env):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "model_terms_required"
    mock_post.return_value = mock_response

    synthesizer = VoiceSynthesizer()

    with patch.object(synthesizer, "_ensure_gtts", return_value=True):
        # We must mock gtts inside generate_speech or sys.modules if it's imported dynamically.
        # It's imported as `from gtts import gTTS`
        with patch.dict('sys.modules', {'gtts': MagicMock()}):
            import sys
            mock_tts_instance = MagicMock()
            sys.modules['gtts'].gTTS.return_value = mock_tts_instance

            success = synthesizer.generate_speech("Test text", "output.mp3", speed=1.0)

            assert success is True
            mock_post.assert_called_once()
            sys.modules['gtts'].gTTS.assert_called_once_with(text="Test text", lang='en')
            mock_tts_instance.save.assert_called_once_with("output.mp3")

@patch("src.interface.voice.requests.post")
@patch("builtins.open", new_callable=mock_open)
def test_voice_synthesizer_generate_speech_with_speed_adjustment(mock_file, mock_post, mock_env):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"fake audio content"
    mock_post.return_value = mock_response

    synthesizer = VoiceSynthesizer()

    with patch.object(synthesizer, "_speed_up_audio", return_value=True) as mock_speed_up:
        success = synthesizer.generate_speech("Test text", "output.opus", speed=1.5)

        assert success is True
        mock_speed_up.assert_called_once_with("output.opus", 1.5)

@patch("os.path.exists")
@patch("os.remove")
@patch("os.rename")
def test_voice_synthesizer_speed_up_audio_success(mock_rename, mock_remove, mock_exists):
    synthesizer = VoiceSynthesizer()

    # The dynamic imports `shutil` and `subprocess` inside _speed_up_audio.
    with patch.dict('sys.modules', {'shutil': MagicMock(), 'subprocess': MagicMock()}):
        import sys
        sys.modules['shutil'].which.return_value = "/usr/bin/ffmpeg"
        sys.modules['subprocess'].run.return_value = MagicMock(returncode=0)
        mock_exists.return_value = True

        success = synthesizer._speed_up_audio("audio.opus", 1.5)

        assert success is True
        sys.modules['subprocess'].run.assert_called_once()
        mock_remove.assert_called_once_with("audio.opus")
        mock_rename.assert_called_once_with("audio.opus.temp.opus", "audio.opus")

def test_voice_synthesizer_speed_up_audio_no_ffmpeg():
    synthesizer = VoiceSynthesizer()
    with patch.dict('sys.modules', {'shutil': MagicMock()}):
        import sys
        sys.modules['shutil'].which.return_value = None

        success = synthesizer._speed_up_audio("audio.opus", 1.5)

        assert success is False
