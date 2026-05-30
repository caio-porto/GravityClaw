import pytest
import sys
from unittest.mock import patch, AsyncMock, MagicMock

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
    from telegram import Update, Message, Chat
    from src.interface.telegram_bridge import handle_message, handle_photo
finally:
    # 3. Restore original modules immediately to preserve test isolation
    for name, orig in _orig_modules.items():
        if orig is not None:
            sys.modules[name] = orig
        else:
            sys.modules.pop(name, None)

@pytest.mark.asyncio
async def test_handle_message():
    """Test the telegram message handler processes text and sends a reply."""
    
    # Mock update
    mock_update = MagicMock(spec=Update)
    mock_message = MagicMock()
    mock_message.text = "Hello agent"
    mock_message.message_id = 1
    mock_message.from_user.username = "test_user"
    mock_message.from_user.id = 123
    mock_update.message = mock_message
    
    mock_chat = MagicMock()
    mock_chat.id = 12345
    mock_update.effective_chat = mock_chat
    
    # Mock context
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    mock_context.bot.send_chat_action = AsyncMock()

    # Patch the global agent
    with patch('src.interface.telegram_bridge.agent.process_input', return_value="I am here.") as mock_process:
        await handle_message(mock_update, mock_context)
        
        # Verify agent processed it
        mock_process.assert_called_once_with("Hello agent", "test_user")
        
        # Verify reply was sent back via telegram
        mock_context.bot.send_message.assert_called_once_with(chat_id=12345, text="I am here.", reply_to_message_id=1)

@pytest.mark.asyncio
async def test_handle_photo():
    """Test the telegram message handler processes photos and sends a reply."""

    # Mock update
    mock_update = MagicMock(spec=Update)
    mock_message = MagicMock()
    mock_message.message_id = 1
    mock_message.from_user.username = "test_user"
    mock_message.from_user.id = 123
    mock_message.caption = "Look at this"

    # Mock photo array
    mock_photo = MagicMock()
    mock_photo.file_id = "test_file_id"
    mock_message.photo = [mock_photo]
    mock_update.message = mock_message

    mock_chat = MagicMock()
    mock_chat.id = 12345
    mock_update.effective_chat = mock_chat

    # Mock context
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    mock_context.bot.send_chat_action = AsyncMock()

    mock_photo_file = AsyncMock()
    mock_context.bot.get_file = AsyncMock(return_value=mock_photo_file)

    # Patch the global agent
    with patch('src.interface.telegram_bridge.agent.process_input', return_value="Cool photo.") as mock_process, \
         patch('os.path.exists', return_value=True) as mock_exists, \
         patch('os.remove') as mock_remove:
        await handle_photo(mock_update, mock_context)

        # Verify file download
        mock_context.bot.get_file.assert_called_once_with("test_file_id")
        mock_photo_file.download_to_drive.assert_called_once_with("temp_photo_test_file_id.jpg")

        # Verify agent processed it
        mock_process.assert_called_once_with("Look at this @temp_photo_test_file_id.jpg", "test_user")

        # Verify file cleanup
        mock_remove.assert_called_once_with("temp_photo_test_file_id.jpg")

        # Verify reply was sent back via telegram
        mock_context.bot.send_message.assert_called_once_with(chat_id=12345, text="Cool photo.", reply_to_message_id=1)

@pytest.mark.asyncio
async def test_handle_photo_error():
    """Test the telegram photo handler processes errors."""

    # Mock update
    mock_update = MagicMock(spec=Update)
    mock_message = MagicMock()
    mock_message.message_id = 1
    mock_message.from_user.username = "test_user"
    mock_message.from_user.id = 123
    mock_message.caption = "Look at this"

    # Mock photo array
    mock_photo = MagicMock()
    mock_photo.file_id = "test_file_id"
    mock_message.photo = [mock_photo]
    mock_update.message = mock_message

    mock_chat = MagicMock()
    mock_chat.id = 12345
    mock_update.effective_chat = mock_chat

    # Mock context
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    mock_context.bot.send_chat_action = AsyncMock()

    mock_photo_file = AsyncMock()
    mock_photo_file.download_to_drive = AsyncMock(side_effect=Exception("Download failed"))
    mock_context.bot.get_file = AsyncMock(return_value=mock_photo_file)

    with patch('os.path.exists', return_value=True) as mock_exists, \
         patch('os.remove') as mock_remove:
        await handle_photo(mock_update, mock_context)

        # Verify error message sent
        mock_context.bot.send_message.assert_called_once_with(chat_id=12345, text="Photo Error: Download failed", reply_to_message_id=1)

        # Verify file cleanup since locals() has file_path
        mock_remove.assert_called_once_with("temp_photo_test_file_id.jpg")
