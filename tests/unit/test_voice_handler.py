import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import io

# Add project root to sys.path
sys.path.append(os.getcwd())

from agent.voice_handler import VoiceHandler

class TestVoiceHandler(unittest.TestCase):
    def setUp(self):
        self.handler = VoiceHandler(api_base="http://mock-localai:8080/v1")

    @patch("openai.resources.audio.transcriptions.Transcriptions.create")
    def test_transcribe(self, mock_create):
        # Mock transcription response
        mock_create.return_value = MagicMock(text="Hello world")
        
        # Dummy audio data (wav header)
        dummy_audio = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x11\x2b\x00\x00\x11\x2b\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00"
        
        # Test without noise reduction (to simplify mock)
        with patch.object(self.handler, 'reduce_noise', return_value=dummy_audio):
            result = self.handler.transcribe(dummy_audio, reduce_noise=False)
            self.assertEqual(result, "Hello world")

    @patch("openai.resources.audio.speech.Speech.create")
    def test_generate_speech(self, mock_create):
        # Mock speech response
        mock_response = MagicMock()
        mock_response.content = b"fake-audio-bytes"
        mock_create.return_value = mock_response
        
        result = self.handler.generate_speech("Hello")
        self.assertEqual(result, b"fake-audio-bytes")

if __name__ == "__main__":
    unittest.main()
