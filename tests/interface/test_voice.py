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
        mock_tts_instance = MagicMock()
        mock_gtts = MagicMock()
        mock_gtts.return_value = mock_tts_instance
        with patch.dict('sys.modules', {'gtts': MagicMock(gTTS=mock_gtts)}):

            success = synthesizer.generate_speech("Test text", "output.mp3", speed=1.0)

            assert success is True
            mock_post.assert_called_once()
            mock_gtts.assert_called_once_with(text="Test text", lang='en')
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
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), patch("subprocess.run", return_value=MagicMock(returncode=0)):
        mock_exists.return_value = True

        success = synthesizer._speed_up_audio("audio.opus", 1.5)

        assert success is True
        import subprocess
        subprocess.run.assert_called_once()
        mock_remove.assert_called_once_with("audio.opus")
        mock_rename.assert_called_once_with("audio.opus.temp.opus", "audio.opus")

def test_voice_synthesizer_speed_up_audio_no_ffmpeg():
    synthesizer = VoiceSynthesizer()
    with patch("shutil.which", return_value=None):

        success = synthesizer._speed_up_audio("audio.opus", 1.5)

        assert success is False

@patch("importlib.util.find_spec")
def test_voice_synthesizer_ensure_gtts_already_installed_flag(mock_find_spec):
    synthesizer = VoiceSynthesizer()
    synthesizer._gtts_installed = True
    assert synthesizer._ensure_gtts() is True
    mock_find_spec.assert_not_called()

@patch("importlib.util.find_spec")
def test_voice_synthesizer_ensure_gtts_found_via_importlib(mock_find_spec):
    synthesizer = VoiceSynthesizer()
    mock_find_spec.return_value = MagicMock() # found
    assert synthesizer._ensure_gtts() is True
    assert synthesizer._gtts_installed is True

@patch("importlib.util.find_spec")
@patch("subprocess.check_call")
def test_voice_synthesizer_ensure_gtts_dynamic_install_success(mock_check_call, mock_find_spec):
    synthesizer = VoiceSynthesizer()
    mock_find_spec.return_value = None # not found

    assert synthesizer._ensure_gtts() is True
    mock_check_call.assert_called_once()
    assert synthesizer._gtts_installed is True

@patch("importlib.util.find_spec")
@patch("subprocess.check_call")
def test_voice_synthesizer_ensure_gtts_dynamic_install_failure(mock_check_call, mock_find_spec):
    import subprocess
    synthesizer = VoiceSynthesizer()
    mock_find_spec.return_value = None # not found
    mock_check_call.side_effect = subprocess.CalledProcessError(1, "pip")

    assert synthesizer._ensure_gtts() is False
    assert synthesizer._gtts_installed is False

@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open, read_data="voice:\n  speed: 1.25\n")
def test_voice_synthesizer_load_speed_from_config_success(mock_file, mock_exists):
    synthesizer = VoiceSynthesizer()
    mock_exists.return_value = True
    assert synthesizer._load_speed_from_config() == 1.25

@patch("os.path.exists")
def test_voice_synthesizer_load_speed_from_config_not_found(mock_exists):
    synthesizer = VoiceSynthesizer()
    mock_exists.return_value = False
    assert synthesizer._load_speed_from_config() == 1.0

@patch("os.path.exists")
@patch("builtins.open", new_callable=mock_open)
def test_voice_synthesizer_load_speed_from_config_exception(mock_file, mock_exists):
    synthesizer = VoiceSynthesizer()
    mock_exists.return_value = True
    mock_file.side_effect = Exception("Read error")
    assert synthesizer._load_speed_from_config() == 1.0

def test_voice_synthesizer_speed_up_audio_speed_1():
    synthesizer = VoiceSynthesizer()
    assert synthesizer._speed_up_audio("audio.opus", 1.0) is True

@patch("os.path.exists")
@patch("os.remove")
def test_voice_synthesizer_speed_up_audio_subprocess_failure(mock_remove, mock_exists):
    synthesizer = VoiceSynthesizer()
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), patch("subprocess.run", return_value=MagicMock(returncode=1, stderr="Error")):
        mock_exists.return_value = True

        success = synthesizer._speed_up_audio("audio.opus", 1.5)

        assert success is False
        import subprocess
        subprocess.run.assert_called_once()
        mock_remove.assert_called_once_with("audio.opus.temp.opus")

@patch("os.path.exists")
@patch("os.remove")
def test_voice_synthesizer_speed_up_audio_subprocess_exception(mock_remove, mock_exists):
    synthesizer = VoiceSynthesizer()
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), patch("subprocess.run", side_effect=Exception("Crash")):
        mock_exists.return_value = True

        success = synthesizer._speed_up_audio("audio.opus", 1.5)

        assert success is False
        import subprocess
        subprocess.run.assert_called_once()
        mock_remove.assert_called_once_with("audio.opus.temp.opus")

@patch("src.interface.voice.requests.post")
@patch("builtins.open", new_callable=mock_open)
def test_voice_synthesizer_generate_speech_speed_none(mock_file, mock_post, mock_env):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"fake audio content"
    mock_post.return_value = mock_response

    synthesizer = VoiceSynthesizer()
    with patch.object(synthesizer, "_load_speed_from_config", return_value=1.5) as mock_load_speed:
        with patch.object(synthesizer, "_speed_up_audio", return_value=True) as mock_speed_up:
            success = synthesizer.generate_speech("Test text", "output.opus", speed=None)

            assert success is True
            mock_load_speed.assert_called_once()
            mock_speed_up.assert_called_once_with("output.opus", 1.5)

@patch("src.interface.voice.requests.post")
def test_voice_synthesizer_generate_speech_groq_exception_gtts_fallback(mock_post, mock_env):
    mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

    synthesizer = VoiceSynthesizer()

    with patch.object(synthesizer, "_ensure_gtts", return_value=True):
        mock_tts_instance = MagicMock()
        mock_gtts = MagicMock()
        mock_gtts.return_value = mock_tts_instance
        with patch.dict('sys.modules', {'gtts': MagicMock(gTTS=mock_gtts)}):

            success = synthesizer.generate_speech("Test text", "output.mp3", speed=1.0)

            assert success is True
            mock_post.assert_called_once()
            mock_gtts.assert_called_once_with(text="Test text", lang='en')

def test_voice_synthesizer_generate_speech_no_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    synthesizer = VoiceSynthesizer()

    with patch.object(synthesizer, "_ensure_gtts", return_value=True):
        mock_tts_instance = MagicMock()
        mock_gtts = MagicMock()
        mock_gtts.return_value = mock_tts_instance
        with patch.dict('sys.modules', {'gtts': MagicMock(gTTS=mock_gtts)}):

            success = synthesizer.generate_speech("Test text", "output.mp3", speed=1.0)

            assert success is True
            mock_gtts.assert_called_once_with(text="Test text", lang='en')

@patch("src.interface.voice.requests.post")
def test_voice_synthesizer_generate_speech_gtts_exception(mock_post, mock_env):
    mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")

    synthesizer = VoiceSynthesizer()

    with patch.object(synthesizer, "_ensure_gtts", return_value=True):
        mock_gtts = MagicMock(side_effect=Exception("gTTS failed"))
        with patch.dict('sys.modules', {'gtts': MagicMock(gTTS=mock_gtts)}):

            success = synthesizer.generate_speech("Test text", "output.mp3", speed=1.0)

            assert success is False

@patch("src.interface.voice.requests.post")
def test_voice_synthesizer_generate_speech_groq_other_error_gtts_fallback(mock_post, mock_env):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_post.return_value = mock_response

    synthesizer = VoiceSynthesizer()

    with patch.object(synthesizer, "_ensure_gtts", return_value=True):
        mock_tts_instance = MagicMock()
        mock_gtts = MagicMock()
        mock_gtts.return_value = mock_tts_instance
        with patch.dict('sys.modules', {'gtts': MagicMock(gTTS=mock_gtts)}):

            success = synthesizer.generate_speech("Test text", "output.mp3", speed=1.0)

            assert success is True
            mock_post.assert_called_once()
            mock_gtts.assert_called_once_with(text="Test text", lang='en')


@patch("src.interface.voice.requests.post")
@patch("builtins.open", new_callable=mock_open, read_data=b"dummy audio data")
def test_voice_processor_transcribe_audio_missing_text(mock_file, mock_post, mock_env):
    mock_response = MagicMock()
    mock_response.json.return_value = {}  # No text key
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    processor = VoiceProcessor()
    result = processor.transcribe_audio("dummy.ogg")

    assert result == ""
