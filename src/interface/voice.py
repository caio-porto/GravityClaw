import os
import requests
import logging

logger = logging.getLogger(__name__)

class VoiceProcessor:
    """Handles audio transcription using Groq's Whisper API (Speech-to-Text)."""
    
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


class VoiceSynthesizer:
    """Handles Text-to-Speech using Groq's Orpheus TTS API."""
    
    def __init__(self, voice: str = "daniel"):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/audio/speech"
        self.voice = voice
        self.model = "canopylabs/orpheus-v1-english"

    def generate_speech(self, text: str, output_path: str) -> bool:
        """Generates speech from text using Groq TTS and saves to output_path.
        
        Returns True on success, False on failure.
        """
        if not self.api_key:
            logger.warning("GROQ_API_KEY is not set, skipping TTS.")
            return False
            
        logger.info(f"Generating TTS for: {text[:80]}...")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": "opus"
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"TTS API returned {response.status_code}: {response.text}")
                return False
            
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            logger.info(f"TTS audio saved to: {output_path} ({len(response.content)} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            return False
