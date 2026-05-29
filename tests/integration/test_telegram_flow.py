import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from telegram import Update, Message, Chat
from src.interface.telegram_bridge import handle_message

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
