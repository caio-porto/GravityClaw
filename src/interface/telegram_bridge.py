import os
import logging
import asyncio
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from src.agent.loop import AgentLoop
from src.interface.voice import VoiceProcessor

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

agent = AgentLoop()
voice_processor = VoiceProcessor()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="GravityClaw V2 initialized. How can I help you today?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_id = str(update.message.from_user.username or update.message.from_user.id)
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    
    try:
        # Run blocking agent logic in a thread to handle concurrent messages
        response = await asyncio.to_thread(agent.process_input, user_input, user_id)
        await context.bot.send_message(chat_id=chat_id, text=response, reply_to_message_id=msg_id)
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"Error: {e}", reply_to_message_id=msg_id)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    user_id = str(update.message.from_user.username or update.message.from_user.id)
    
    try:
        # Download the voice file
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        file_path = f"temp_voice_{update.message.voice.file_id}.ogg"
        await voice_file.download_to_drive(file_path)
        
        # Transcribe
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        transcription = await asyncio.to_thread(voice_processor.transcribe_audio, file_path)
        
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
            
        if not transcription:
            await context.bot.send_message(chat_id=chat_id, text="Could not transcribe audio.", reply_to_message_id=msg_id)
            return
            
        # Send transcription to agent loop
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        response = await asyncio.to_thread(agent.process_input, transcription, user_id)
        await context.bot.send_message(chat_id=chat_id, text=response, reply_to_message_id=msg_id)
        
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"Voice Error: {e}", reply_to_message_id=msg_id)

async def run_bot_async(stop_event: asyncio.Event):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment.")

    application = ApplicationBuilder().token(token).build()

    start_handler = CommandHandler('start', start)
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    voice_handler = MessageHandler(filters.VOICE, handle_voice)

    application.add_handler(start_handler)
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
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    voice_handler = MessageHandler(filters.VOICE, handle_voice)
    
    application.add_handler(start_handler)
    application.add_handler(message_handler)
    application.add_handler(voice_handler)
    
    logging.info("Starting Telegram polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
