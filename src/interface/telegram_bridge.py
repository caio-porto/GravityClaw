import os
import logging
import asyncio
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

agent = AgentLoop()
voice_processor = VoiceProcessor()
voice_synthesizer = VoiceSynthesizer()

# Store user preferences for voice mode (True means always reply with voice)
user_voice_mode = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="GravityClaw initialized. How can I help you today?\nUse /voice_toggle to toggle voice responses for text messages.")

async def voice_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    current_mode = user_voice_mode.get(chat_id, True)
    user_voice_mode[chat_id] = not current_mode
    status = "enabled" if user_voice_mode[chat_id] else "disabled"
    await context.bot.send_message(chat_id=chat_id, text=f"Voice responses for text messages are now {status}.")

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
        
        # Then send voice unless user has opted out via /voice_toggle
        if user_voice_mode.get(chat_id, True):
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

async def run_bot_async(stop_event: asyncio.Event):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment.")

    application = ApplicationBuilder().token(token).build()

    start_handler = CommandHandler('start', start)
    toggle_handler = CommandHandler('voice_toggle', voice_toggle)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    voice_handler = MessageHandler(filters.VOICE, handle_voice)

    application.add_handler(start_handler)
    application.add_handler(toggle_handler)
    application.add_handler(message_handler)
    application.add_handler(voice_handler)

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
    
    application.add_handler(start_handler)
    application.add_handler(toggle_handler)
    application.add_handler(message_handler)
    application.add_handler(voice_handler)
    
    logging.info("Starting Telegram polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
