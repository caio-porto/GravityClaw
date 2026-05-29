import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from telegram import Update
from src.interface.telegram_bridge import _send_response

@pytest.mark.asyncio
async def test_send_response_with_image_tag():
    """Test that _send_response parses [IMAGE: prompt] tags, cleans the response, and calls send_photo."""
    mock_update = MagicMock(spec=Update)
    mock_message = MagicMock()
    mock_message.message_id = 42
    mock_message.from_user.username = "caio"
    mock_update.message = mock_message
    
    mock_chat = MagicMock()
    mock_chat.id = 12345
    mock_update.effective_chat = mock_chat
    
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    mock_context.bot.send_photo = AsyncMock()
    mock_context.bot.send_chat_action = AsyncMock()
    
    # Raw agent response containing the [IMAGE: prompt] tag
    raw_response = "Sure, Caio! Here is your picture:\n[IMAGE: a beautiful high-resolution photo of a Rivian R2 electric SUV driving on a highway]"
    
    # We patch _should_send_voice to return False so we only test text/photo flow
    with patch('src.interface.telegram_bridge._should_send_voice', return_value=False):
        await _send_response(mock_update, mock_context, raw_response, user_input="Send me a picture of a Rivian R2", is_voice_input=False)
        
        # 1. Verify clean text was sent (without the [IMAGE: ...] tag)
        expected_clean_text = "Sure, Caio! Here is your picture:"
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=12345,
            text=expected_clean_text,
            reply_to_message_id=42
        )
        
        # 2. Verify that send_photo was called with the correctly URL-encoded Pollinations.ai endpoint
        expected_photo_url = "https://image.pollinations.ai/prompt/a%20beautiful%20high-resolution%20photo%20of%20a%20Rivian%20R2%20electric%20SUV%20driving%20on%20a%20highway?width=1024&height=1024&nologo=true&private=true"
        expected_caption = "🎨 Generated: a beautiful high-resolution photo of a Rivian R2 electric SUV driving on a highway"
        
        mock_context.bot.send_photo.assert_called_once_with(
            chat_id=12345,
            photo=expected_photo_url,
            caption=expected_caption,
            reply_to_message_id=42
        )

@pytest.mark.asyncio
async def test_send_response_multiple_image_tags():
    """Test that _send_response supports extracting and dispatching multiple image tags in a single turn."""
    mock_update = MagicMock(spec=Update)
    mock_message = MagicMock()
    mock_message.message_id = 99
    mock_update.message = mock_message
    
    mock_chat = MagicMock()
    mock_chat.id = 12345
    mock_update.effective_chat = mock_chat
    
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    mock_context.bot.send_photo = AsyncMock()
    mock_context.bot.send_chat_action = AsyncMock()
    
    raw_response = "Here are two concepts: [IMAGE: red car] and [IMAGE: blue car]."
    
    with patch('src.interface.telegram_bridge._should_send_voice', return_value=False):
        await _send_response(mock_update, mock_context, raw_response, user_input="Show me two concepts", is_voice_input=False)
        
        # 1. Verify clean text sent
        expected_clean_text = "Here are two concepts:  and ."
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=12345,
            text=expected_clean_text,
            reply_to_message_id=99
        )
        
        # 2. Verify that two photos were sent
        self_calls = mock_context.bot.send_photo.call_args_list
        assert len(self_calls) == 2
        
        # First call details
        assert self_calls[0][1]['photo'] == "https://image.pollinations.ai/prompt/red%20car?width=1024&height=1024&nologo=true&private=true"
        assert self_calls[0][1]['caption'] == "🎨 Generated: red car"
        
        # Second call details
        assert self_calls[1][1]['photo'] == "https://image.pollinations.ai/prompt/blue%20car?width=1024&height=1024&nologo=true&private=true"
        assert self_calls[1][1]['caption'] == "🎨 Generated: blue car"

@pytest.mark.asyncio
async def test_send_response_with_internet_image_url():
    """Test that _send_response parses [IMAGE_URL: url] tags, cleans them, downloads the image, and uploads it."""
    mock_update = MagicMock(spec=Update)
    mock_message = MagicMock()
    mock_message.message_id = 100
    mock_update.message = mock_message
    
    mock_chat = MagicMock()
    mock_chat.id = 12345
    mock_update.effective_chat = mock_chat
    
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    mock_context.bot.send_photo = AsyncMock()
    mock_context.bot.send_chat_action = AsyncMock()
    
    raw_response = "Here is a real Rivian R2 from the web: [IMAGE_URL: https://upload.wikimedia.org/wikipedia/commons/e/ea/Rivian_R2_Front_View.jpg]"
    
    # Mock requests.get response
    mock_response = MagicMock()
    mock_response.content = b"fake-image-data-bytes"
    mock_response.status_code = 200
    
    with patch('src.interface.telegram_bridge._should_send_voice', return_value=False), \
         patch('requests.get', return_value=mock_response) as mock_get:
         
        await _send_response(mock_update, mock_context, raw_response, user_input="Send me a picture of a Rivian R2 from the internet", is_voice_input=False)
        
        # 1. Verify requests.get was called
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert args[0] == "https://upload.wikimedia.org/wikipedia/commons/e/ea/Rivian_R2_Front_View.jpg"
        assert "User-Agent" in kwargs["headers"]
        
        # 2. Verify clean text sent
        expected_clean_text = "Here is a real Rivian R2 from the web:"
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=12345,
            text=expected_clean_text,
            reply_to_message_id=100
        )
        
        # 3. Verify that send_photo was called with the uploaded file object and caption
        mock_context.bot.send_photo.assert_called_once()
        photo_args, photo_kwargs = mock_context.bot.send_photo.call_args
        assert photo_kwargs['chat_id'] == 12345
        assert photo_kwargs['reply_to_message_id'] == 100
        assert photo_kwargs['caption'] == "🌐 Image from Internet: https://upload.wikimedia.org/wikipedia/commons/e/ea/Rivian_R2_Front_View.jpg"
        assert hasattr(photo_kwargs['photo'], 'read')
