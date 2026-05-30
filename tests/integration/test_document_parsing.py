import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from telegram import Update
import os

from src.interface.telegram_bridge import handle_document

@pytest.mark.asyncio
async def test_handle_document():
    """Test that handle_document successfully downloads, processes, and cleans up document files."""
    mock_update = MagicMock(spec=Update)
    mock_message = MagicMock()
    mock_message.message_id = 42
    mock_message.from_user.username = "caio"
    mock_message.caption = "Read this invoice"

    # Mock document attachment
    mock_document = MagicMock()
    mock_document.file_id = "test_doc_123"
    mock_document.file_name = "invoice.pdf"
    mock_message.document = mock_document

    mock_update.message = mock_message

    mock_chat = MagicMock()
    mock_chat.id = 12345
    mock_update.effective_chat = mock_chat

    mock_context = MagicMock()
    mock_document_file = AsyncMock()
    # Mock download_to_drive to actually create the dummy file to test cleanup
    async def mock_download_to_drive(file_path):
        with open(file_path, "w") as f:
            f.write("dummy pdf content")

    mock_document_file.download_to_drive.side_effect = mock_download_to_drive
    mock_context.bot.get_file = AsyncMock(return_value=mock_document_file)
    mock_context.bot.send_message = AsyncMock()
    mock_context.bot.send_chat_action = AsyncMock()

    mock_response_text = "The invoice total is $100."

    expected_file_path = "temp_doc_test_doc_123.pdf"
    expected_prompt = f"Read this invoice @{expected_file_path}"

    with patch('src.interface.telegram_bridge.agent.process_input', return_value=mock_response_text) as mock_agent_process, \
         patch('src.interface.telegram_bridge._send_response', new_callable=AsyncMock) as mock_send_response:

        await handle_document(mock_update, mock_context)

        # 1. Verify agent was called with correct prompt including file path
        mock_agent_process.assert_called_once_with(expected_prompt, "caio")

        # 2. Verify _send_response was called
        mock_send_response.assert_called_once_with(mock_update, mock_context, mock_response_text, user_input="Read this invoice", is_voice_input=False)

        # 3. Verify the temporary file was cleaned up
        assert not os.path.exists(expected_file_path)
