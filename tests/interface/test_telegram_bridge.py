import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Mock src.memory to avoid ModuleNotFoundError since it doesn't seem to exist
import sys
from unittest.mock import MagicMock

# 1. Save original modules to prevent test pollution
_orig_modules = {
    'src.memory': sys.modules.get('src.memory'),
    'src.memory.core': sys.modules.get('src.memory.core'),
    'src.memory.buffer': sys.modules.get('src.memory.buffer'),
    'src.agent.loop': sys.modules.get('src.agent.loop'),
}

# 2. Temporarily inject mocks for the duration of the imports
sys.modules['src.memory'] = MagicMock()
sys.modules['src.memory.core'] = MagicMock()
sys.modules['src.memory.buffer'] = MagicMock()
sys.modules['src.agent.loop'] = MagicMock()

try:
    from src.interface.telegram_bridge import run_bot_async
finally:
    # 3. Restore original modules immediately to preserve test isolation
    for name, orig in _orig_modules.items():
        if orig is not None:
            sys.modules[name] = orig
        else:
            sys.modules.pop(name, None)

@pytest.mark.asyncio
async def test_run_bot_async_missing_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    stop_event = asyncio.Event()
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN is not set in environment."):
        await run_bot_async(stop_event)

@pytest.mark.asyncio
@patch("src.interface.telegram_bridge.ApplicationBuilder")
@patch("src.interface.telegram_bridge.CommandHandler")
@patch("src.interface.telegram_bridge.MessageHandler")
@patch("src.interface.telegram_bridge.asyncio.sleep", new_callable=AsyncMock)
async def test_run_bot_async_success(mock_sleep, mock_message_handler, mock_command_handler, mock_builder, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_token")

    mock_app = MagicMock()
    mock_app.initialize = AsyncMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()
    mock_app.shutdown = AsyncMock()
    mock_app.updater = MagicMock()
    mock_app.updater.start_polling = AsyncMock()
    mock_app.updater.stop = AsyncMock()

    mock_builder_instance = MagicMock()
    mock_builder.return_value = mock_builder_instance
    mock_builder_instance.token.return_value = mock_builder_instance
    mock_builder_instance.build.return_value = mock_app

    stop_event = asyncio.Event()

    # We want the loop to run once, then exit.
    # mock_sleep will just set the stop_event when it's called.
    async def mock_sleep_impl(delay):
        stop_event.set()

    mock_sleep.side_effect = mock_sleep_impl

    await run_bot_async(stop_event)

    # Assertions
    mock_builder.assert_called_once()
    mock_builder_instance.token.assert_called_once_with("fake_token")
    mock_builder_instance.build.assert_called_once()

    # Check if handlers are added
    assert mock_app.add_handler.call_count == 6

    mock_app.initialize.assert_awaited_once()
    mock_app.start.assert_awaited_once()
    mock_app.updater.start_polling.assert_awaited_once()

    mock_sleep.assert_awaited_once_with(0.5)

    mock_app.updater.stop.assert_awaited_once()
    mock_app.stop.assert_awaited_once()
    mock_app.shutdown.assert_awaited_once()

@pytest.mark.asyncio
@patch("src.interface.telegram_bridge.bot_instance")
@patch("src.interface.telegram_bridge._load_config")
async def test_send_telegram_message(mock_load_config, mock_bot):
    from src.interface.telegram_bridge import send_telegram_message

    # Configure mock bot
    mock_bot.send_message = AsyncMock()

    # Mock config with chat id
    mock_load_config.return_value = {"telegram": {"last_chat_id": 12345}}

    result = await send_telegram_message("Test message")

    assert result is True
    mock_bot.send_message.assert_called_once_with(chat_id=12345, text="Test message")

@pytest.mark.asyncio
@patch("src.interface.telegram_bridge._save_config")
@patch("src.interface.telegram_bridge._load_config")
async def test_update_last_chat_id(mock_load_config, mock_save_config):
    from src.interface.telegram_bridge import _update_last_chat_id

    mock_load_config.return_value = {"telegram": {"last_chat_id": 111}}

    _update_last_chat_id(222)

    mock_save_config.assert_called_once()
    saved_conf = mock_save_config.call_args[0][0]
    assert saved_conf["telegram"]["last_chat_id"] == 222