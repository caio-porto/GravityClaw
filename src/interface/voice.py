import os
import requests
import logging

logger = logging.getLogger(__name__)

class VoiceProcessor:
    """Handles audio transcription using Groq's Whisper API."""
    
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/audio/transcriptions"

    def transcribe_audio(self, file_path: str) -> str:
        """Transcribes the given audio file using Groq's Whisper API."""
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not set.")
            
        logger.info(f"Transcribing audio file: {file_path}")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        with open(file_path, "rb") as f:
            files = {
                "file": (os.path.basename(file_path), f, "audio/ogg"),
            }
            data = {
                "model": "whisper-large-v3",
                "response_format": "json"
            }
            
            response = requests.post(self.api_url, headers=headers, files=files, data=data)
            
        response.raise_for_status()
        result = response.json()
        
        transcription = result.get("text", "")
        logger.info(f"Transcription successful: {transcription}")
        return transcription
