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
    """Handles Text-to-Speech using Groq's Orpheus TTS API with automatic gTTS fallback."""
    
    def __init__(self, voice: str = "daniel"):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/audio/speech"
        self.voice = voice
        self.model = "canopylabs/orpheus-v1-english"
        self._gtts_installed = False

    def _ensure_gtts(self) -> bool:
        """Dynamically ensures gTTS is installed for fallback."""
        if self._gtts_installed:
            return True
        try:
            import gtts
            self._gtts_installed = True
            return True
        except ImportError:
            logger.info("gTTS not installed. Attempting dynamic installation...")
            import subprocess
            import sys
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "gTTS"])
                self._gtts_installed = True
                logger.info("gTTS installed successfully!")
                return True
            except Exception as e:
                logger.error(f"Failed to dynamically install gTTS: {e}")
                return False

    def generate_speech(self, text: str, output_path: str) -> bool:
        """Generates speech from text using Groq TTS, falling back to gTTS if Groq fails or is not configured.
        
        Returns True on success, False on failure.
        """
        # Try Groq TTS first if API key is set
        if self.api_key:
            logger.info(f"Attempting Groq Orpheus TTS for: {text[:80]}...")
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
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=15)
                if response.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(response.content)
                    logger.info(f"Groq TTS audio saved to: {output_path} ({len(response.content)} bytes)")
                    return True
                else:
                    err_msg = response.text
                    if "model_terms_required" in err_msg or "requires terms acceptance" in err_msg:
                        logger.error("Groq TTS failed: Terms acceptance required for the Orpheus model! "
                                     "Please accept terms at https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english")
                    else:
                        logger.error(f"Groq TTS API returned {response.status_code}: {err_msg}")
            except Exception as e:
                logger.error(f"Groq TTS generation request failed: {e}")
        else:
            logger.warning("GROQ_API_KEY is not set. Skipping Groq TTS.")

        # Fallback to gTTS
        logger.info("Falling back to gTTS (Google Text-to-Speech)...")
        if self._ensure_gtts():
            try:
                from gtts import gTTS
                tts = gTTS(text=text, lang='en')
                tts.save(output_path)
                logger.info(f"gTTS audio saved successfully to: {output_path}")
                return True
            except Exception as e:
                logger.error(f"gTTS generation failed: {e}")
        
        return False
