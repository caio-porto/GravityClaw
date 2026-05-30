import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from telegram import Update, Message, Chat, Voice
import os

from src.interface.telegram_bridge import handle_voice

@pytest.mark.asyncio
async def test_handle_voice_success():
    """Test the telegram voice handler correctly downloads, transcribes, processes, and replies."""

    # Mock update
    mock_update = MagicMock(spec=Update)
    mock_message = MagicMock()
    mock_message.message_id = 1
    mock_message.from_user.username = "test_user"
    mock_message.from_user.id = 123

    # Mock voice part of the message
    mock_voice = MagicMock(spec=Voice)
    mock_voice.file_id = "test_file_id"
    mock_message.voice = mock_voice
    mock_update.message = mock_message

    mock_chat = MagicMock()
    mock_chat.id = 12345
    mock_update.effective_chat = mock_chat

    # Mock context
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    mock_context.bot.send_chat_action = AsyncMock()
    mock_context.bot.send_voice = AsyncMock()

    # Mock get_file behavior
    mock_voice_file = MagicMock()
    mock_voice_file.download_to_drive = AsyncMock()
    mock_context.bot.get_file = AsyncMock(return_value=mock_voice_file)

    # Patch the global agent, voice processor, voice synthesizer and os.path/remove
    with patch('src.interface.telegram_bridge.agent.process_input', return_value="Here is your answer.") as mock_process, \
         patch('src.interface.telegram_bridge.voice_processor.transcribe_audio', return_value="What is your purpose?") as mock_transcribe, \
         patch('src.interface.telegram_bridge.voice_synthesizer.generate_speech', return_value=True) as mock_generate_speech, \
         patch('src.interface.telegram_bridge.os.path.exists', return_value=True) as mock_exists, \
         patch('src.interface.telegram_bridge.os.remove') as mock_remove:

        # also mock builtin open so _send_response can "open" the generated audio file
        with patch("builtins.open", new_callable=MagicMock):
            await handle_voice(mock_update, mock_context)

        # Verify voice file was requested
        mock_context.bot.get_file.assert_called_once_with("test_file_id")

        # Verify transcription was called with expected path
        mock_transcribe.assert_called_once_with("temp_voice_test_file_id.ogg")

        # Verify agent processed the transcription
        mock_process.assert_called_once_with("What is your purpose?", "test_user")

        # Verify cleanup was called
        mock_remove.assert_any_call("temp_voice_test_file_id.ogg")

        # _send_response uses voice since is_voice_input=True
        # Since voice is on, and it generates speech correctly, send_voice should be called
        mock_context.bot.send_voice.assert_called_once()


@pytest.mark.asyncio
async def test_handle_voice_transcription_failure():
    """Test the telegram voice handler correctly handles transcription failure."""

    # Mock update
    mock_update = MagicMock(spec=Update)
    mock_message = MagicMock()
    mock_message.message_id = 1
    mock_message.from_user.username = "test_user"
    mock_message.from_user.id = 123

    # Mock voice part of the message
    mock_voice = MagicMock(spec=Voice)
    mock_voice.file_id = "test_file_id"
    mock_message.voice = mock_voice
    mock_update.message = mock_message

    mock_chat = MagicMock()
    mock_chat.id = 12345
    mock_update.effective_chat = mock_chat

    # Mock context
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    mock_context.bot.send_chat_action = AsyncMock()

    # Mock get_file behavior
    mock_voice_file = MagicMock()
    mock_voice_file.download_to_drive = AsyncMock()
    mock_context.bot.get_file = AsyncMock(return_value=mock_voice_file)

    # Patch the global agent, voice processor, voice synthesizer and os.path/remove
    with patch('src.interface.telegram_bridge.agent.process_input', return_value="Here is your answer.") as mock_process, \
         patch('src.interface.telegram_bridge.voice_processor.transcribe_audio', return_value="") as mock_transcribe, \
         patch('src.interface.telegram_bridge.os.path.exists', return_value=True) as mock_exists, \
         patch('src.interface.telegram_bridge.os.remove') as mock_remove:

        await handle_voice(mock_update, mock_context)

        # Verify voice file was requested
        mock_context.bot.get_file.assert_called_once_with("test_file_id")

        # Verify transcription was called with expected path
        mock_transcribe.assert_called_once_with("temp_voice_test_file_id.ogg")

        # Verify agent was NOT called
        mock_process.assert_not_called()

        # Verify cleanup was called
        mock_remove.assert_any_call("temp_voice_test_file_id.ogg")

        # Verify a failure message was sent to the user
        mock_context.bot.send_message.assert_called_once_with(chat_id=12345, text="Could not transcribe audio.", reply_to_message_id=1)

@pytest.mark.asyncio
async def test_handle_voice_exception():
    """Test the telegram voice handler correctly handles exceptions during processing."""

    # Mock update
    mock_update = MagicMock(spec=Update)
    mock_message = MagicMock()
    mock_message.message_id = 1
    mock_message.from_user.username = "test_user"
    mock_message.from_user.id = 123

    # Mock voice part of the message
    mock_voice = MagicMock(spec=Voice)
    mock_voice.file_id = "test_file_id"
    mock_message.voice = mock_voice
    mock_update.message = mock_message

    mock_chat = MagicMock()
    mock_chat.id = 12345
    mock_update.effective_chat = mock_chat

    # Mock context
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    mock_context.bot.send_chat_action = AsyncMock()

    # Mock get_file behavior
    mock_voice_file = MagicMock()
    mock_voice_file.download_to_drive = AsyncMock(side_effect=Exception("Download failed"))
    mock_context.bot.get_file = AsyncMock(return_value=mock_voice_file)

    await handle_voice(mock_update, mock_context)

    # Verify voice file was requested
    mock_context.bot.get_file.assert_called_once_with("test_file_id")

    # Verify a failure message was sent to the user
    mock_context.bot.send_message.assert_called_once_with(chat_id=12345, text="Voice Error: Download failed", reply_to_message_id=1)
