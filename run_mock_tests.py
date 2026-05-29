import os
import unittest
from unittest.mock import patch, MagicMock

# Import the components to test
from src.agent.loop import AgentLoop, ModelManager
from src.interface.voice import VoiceProcessor

class TestGravityClawEndToEnd(unittest.TestCase):

    def setUp(self):
        # We don't need real API keys for mocked tests
        os.environ["GROQ_API_KEY"] = "mock_key"
        self.agent = AgentLoop()

    @patch('src.agent.loop.subprocess.run')
    def test_1_normal_prompt(self, mock_run):
        """Test a normal prompt hitting the primary model."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "yolo mode enabled\nloaded cached credentials\nGemini: Hello! I am your primary model."
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        response = self.agent.process_input("Hi there!")
        
        # Verify it invoked gemini CLI via subprocess
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args[0][0][0], "gemini")
        # The prompt is now the last argument (flattened messages)
        prompt_arg = mock_run.call_args[0][0][-1]
        self.assertIn("Hi there!", prompt_arg)
        self.assertEqual(response, "Hello! I am your primary model.")

    @patch('src.agent.loop.ModelManager._query_antigravity')
    @patch('src.agent.loop.ModelManager._query_groq')
    def test_2_fallback_to_groq(self, mock_groq, mock_primary):
        """Test that a failure in the primary model falls back to Groq."""
        # Force primary to fail
        mock_primary.side_effect = Exception("Connection Refused")
        # Set Groq fallback response
        mock_groq.return_value = "I am the Groq fallback model."

        response = self.agent.process_input("Are you there?")
        
        mock_primary.assert_called_once()
        mock_groq.assert_called_once()
        self.assertEqual(response, "I am the Groq fallback model.")

    @patch('src.agent.loop.ModelManager._query_antigravity')
    @patch('src.agent.loop.ModelManager._query_groq')
    @patch('src.agent.loop.ModelManager._query_ollama')
    def test_3_fallback_to_ollama(self, mock_ollama, mock_groq, mock_primary):
        """Test that a failure in primary AND Groq falls back to Ollama."""
        mock_primary.side_effect = Exception("Primary Down")
        mock_groq.side_effect = Exception("Groq Rate Limit")
        mock_ollama.return_value = "I am the Ollama fallback model."

        response = self.agent.process_input("Emergency!")
        
        mock_primary.assert_called_once()
        mock_groq.assert_called_once()
        mock_ollama.assert_called_once()
        self.assertEqual(response, "I am the Ollama fallback model.")

    @patch('src.interface.voice.requests.post')
    def test_4_voice_transcription(self, mock_post):
        """Test that the VoiceProcessor correctly parses the Groq Whisper response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"text": "This is a transcribed voice note."}
        mock_post.return_value = mock_response

        # We need a dummy file to pass to the open() function
        with open("dummy.ogg", "w") as f:
            f.write("dummy audio data")

        processor = VoiceProcessor()
        text = processor.transcribe_audio("dummy.ogg")
        
        self.assertEqual(text, "This is a transcribed voice note.")
        
        # Cleanup
        os.remove("dummy.ogg")

if __name__ == '__main__':
    unittest.main(verbosity=2)
