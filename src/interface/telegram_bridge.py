import os
import logging
import asyncio
import yaml
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from src.agent.loop import AgentLoop
from src.interface.voice import VoiceProcessor, VoiceSynthesizer

logger = logging.getLogger(__name__)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def _load_config():
    try:
        if os.path.exists("config.yaml"):
            with open("config.yaml", "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
    return {}

def _save_config(config):
    try:
        with open("config.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")

agent = AgentLoop()
voice_processor = VoiceProcessor()
voice_synthesizer = VoiceSynthesizer()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="GravityClaw initialized. How can I help you today?\nUse /voice_toggle to cycle through voice response modes (Always, Auto, Off).")

async def voice_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    config = _load_config()
    voice_cfg = config.setdefault("voice", {})
    current_mode = voice_cfg.get("mode", "auto")
    
    modes = ["always", "auto", "off"]
    new_mode = modes[(modes.index(current_mode) + 1) % len(modes)]
    
    voice_cfg["mode"] = new_mode
    _save_config(config)
    
    status_map = {
        "always": "Always-On (Replies to everything with voice)",
        "auto": "Auto (Smart: Keywords or reply to voice only)",
        "off": "Off (Disabled voice for text/photos)"
    }
    
    await context.bot.send_message(chat_id=chat_id, text=f"Voice response mode is now: {status_map[new_mode]}")

async def _should_send_voice(text, is_voice_input=False):
    """Determine if we should send a voice response based on config and input."""
    config = _load_config()
    voice_cfg = config.get("voice", {})
    mode = voice_cfg.get("mode", "auto")
    
    if mode == "always":
        return True
    if mode == "off":
        return False
    
    # Auto mode logic
    if is_voice_input:
        return True
    
    if not text:
        return False

    text_lower = text.lower()
    
    # Explicit phrases for voice request
    trigger_phrases = [
        "respond in voice", "responda em voz", "manda áudio", "manda audio",
        "send voice", "voice message", "me fale", "speak to me", "vocalize",
        "fale em voz", "say it", "diga em voz"
    ]
    if any(phrase in text_lower for phrase in trigger_phrases):
        return True
        
    # Command-like prefixes (e.g., "Say: Hello" or "Fale o que você acha")
    words = text_lower.split()
    if words:
        first_word = words[0].rstrip(':,')
        if first_word in ["say", "fale", "speak", "diga"]:
            return True

    return False

async def _keep_typing(bot, chat_id: int, cancel_event: asyncio.Event, action=ChatAction.TYPING):
    """Continuously send specific chat action every 4s until cancel_event is set."""
    try:
        while not cancel_event.is_set():
            await bot.send_chat_action(chat_id=chat_id, action=action)
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                pass  # timeout means we loop and send action again
    except Exception:
        pass  # silently stop if the chat action fails

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_id = str(update.message.from_user.username or update.message.from_user.id)
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    
    cancel_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(context.bot, chat_id, cancel_typing))
    
    try:
        response = await asyncio.to_thread(agent.process_input, user_input, user_id)
        cancel_typing.set()
        await typing_task
        
        # Always send text first
        await context.bot.send_message(chat_id=chat_id, text=response, reply_to_message_id=msg_id)
        
        # Then send voice if appropriate
        if await _should_send_voice(user_input):
            reply_audio_path = f"reply_voice_{msg_id}.opus"
            try:
                cancel_voice = asyncio.Event()
                voice_task = asyncio.create_task(_keep_typing(context.bot, chat_id, cancel_voice, ChatAction.RECORD_VOICE))
                success = await asyncio.to_thread(voice_synthesizer.generate_speech, response, reply_audio_path)
                cancel_voice.set()
                await voice_task
                if success and os.path.exists(reply_audio_path):
                    with open(reply_audio_path, "rb") as f:
                        await context.bot.send_voice(chat_id=chat_id, voice=f, reply_to_message_id=msg_id)
            except Exception as e:
                logger.warning(f"TTS failed for text message, skipping voice: {e}")
            finally:
                if os.path.exists(reply_audio_path):
                    os.remove(reply_audio_path)
    except Exception as e:
        cancel_typing.set()
        await typing_task
        await context.bot.send_message(chat_id=chat_id, text=f"Error: {e}", reply_to_message_id=msg_id)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    user_id = str(update.message.from_user.username or update.message.from_user.id)
    
    cancel_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(context.bot, chat_id, cancel_typing))
    
    try:
        # Download the voice file
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        file_path = f"temp_voice_{update.message.voice.file_id}.ogg"
        await voice_file.download_to_drive(file_path)
        
        # Transcribe
        transcription = await asyncio.to_thread(voice_processor.transcribe_audio, file_path)
        
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
            
        if not transcription:
            cancel_typing.set()
            await typing_task
            await context.bot.send_message(chat_id=chat_id, text="Could not transcribe audio.", reply_to_message_id=msg_id)
            return
            
        # Send transcription to agent loop
        response = await asyncio.to_thread(agent.process_input, transcription, user_id)
        cancel_typing.set()
        await typing_task
        
        # Generate and send voice response since user used voice
        cancel_voice = asyncio.Event()
        voice_task = asyncio.create_task(_keep_typing(context.bot, chat_id, cancel_voice, ChatAction.RECORD_VOICE))
        reply_audio_path = f"reply_voice_{msg_id}.opus"
        try:
            success = await asyncio.to_thread(voice_synthesizer.generate_speech, response, reply_audio_path)
            cancel_voice.set()
            await voice_task
            if success and os.path.exists(reply_audio_path):
                with open(reply_audio_path, "rb") as f:
                    await context.bot.send_voice(chat_id=chat_id, voice=f, caption=response[:1024], reply_to_message_id=msg_id)
            else:
                # Fallback to text if TTS fails
                await context.bot.send_message(chat_id=chat_id, text=response, reply_to_message_id=msg_id)
        finally:
            if os.path.exists(reply_audio_path):
                os.remove(reply_audio_path)
        
    except Exception as e:
        cancel_typing.set()
        await typing_task
        await context.bot.send_message(chat_id=chat_id, text=f"Voice Error: {e}", reply_to_message_id=msg_id)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    user_id = str(update.message.from_user.username or update.message.from_user.id)
    caption = update.message.caption or "Analyze this image."
    
    cancel_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(context.bot, chat_id, cancel_typing))
    
    try:
        # Download high-res photo file
        photo = update.message.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)
        file_path = f"temp_photo_{photo.file_id}.jpg"
        await photo_file.download_to_drive(file_path)
        
        # Build prompt with @path reference
        prompt_with_image = f"{caption} @{file_path}"
        
        # Send prompt with image to agent loop
        response = await asyncio.to_thread(agent.process_input, prompt_with_image, user_id)
        cancel_typing.set()
        await typing_task
        
        # Clean up local temp photo file
        if os.path.exists(file_path):
            os.remove(file_path)
            
        # Always send text first
        await context.bot.send_message(chat_id=chat_id, text=response, reply_to_message_id=msg_id)
        
        # Then send voice if appropriate
        if await _should_send_voice(caption):
            reply_audio_path = f"reply_voice_{msg_id}.opus"
            try:
                cancel_voice = asyncio.Event()
                voice_task = asyncio.create_task(_keep_typing(context.bot, chat_id, cancel_voice, ChatAction.RECORD_VOICE))
                success = await asyncio.to_thread(voice_synthesizer.generate_speech, response, reply_audio_path)
                cancel_voice.set()
                await voice_task
                if success and os.path.exists(reply_audio_path):
                    with open(reply_audio_path, "rb") as f:
                        await context.bot.send_voice(chat_id=chat_id, voice=f, reply_to_message_id=msg_id)
            except Exception as e:
                logger.warning(f"TTS failed for photo message, skipping voice: {e}")
            finally:
                if os.path.exists(reply_audio_path):
                    os.remove(reply_audio_path)
                    
    except Exception as e:
        cancel_typing.set()
        await typing_task
        await context.bot.send_message(chat_id=chat_id, text=f"Photo Error: {e}", reply_to_message_id=msg_id)
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

async def run_bot_async(stop_event: asyncio.Event):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment.")

    application = ApplicationBuilder().token(token).build()

    start_handler = CommandHandler('start', start)
    toggle_handler = CommandHandler('voice_toggle', voice_toggle)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    voice_handler = MessageHandler(filters.VOICE, handle_voice)
    photo_handler = MessageHandler(filters.PHOTO, handle_photo)

    application.add_handler(start_handler)
    application.add_handler(toggle_handler)
    application.add_handler(message_handler)
    application.add_handler(voice_handler)
    application.add_handler(photo_handler)

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    logging.info("Starting asynchronous Telegram polling...")
    try:
        while not stop_event.is_set():
            await asyncio.sleep(0.5)
    finally:
        logging.info("Stopping asynchronous Telegram polling...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment.")
    
    application = ApplicationBuilder().token(token).build()
    
    start_handler = CommandHandler('start', start)
    toggle_handler = CommandHandler('voice_toggle', voice_toggle)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    voice_handler = MessageHandler(filters.VOICE, handle_voice)
    photo_handler = MessageHandler(filters.PHOTO, handle_photo)
    
    application.add_handler(start_handler)
    application.add_handler(toggle_handler)
    application.add_handler(message_handler)
    application.add_handler(voice_handler)
    application.add_handler(photo_handler)
    
    logging.info("Starting Telegram polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
