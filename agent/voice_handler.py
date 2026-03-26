import os
import io
import wave
import numpy as np
import noisereduce as nr
from pydub import AudioSegment
from openai import OpenAI
from typing import Optional

class VoiceHandler:
    """Handles audio preprocessing, STT (Whisper), and TTS using LocalAI."""

    def __init__(self, api_base: Optional[str] = None):
        self.api_base = api_base or os.getenv("LOCALAI_API_BASE", "http://localhost:8080/v1")
        self.client = OpenAI(api_key="not-needed", base_url=self.api_base)
        self.whisper_model = os.getenv("WHISPER_MODEL", "whisper-1")
        self.tts_model = os.getenv("TTS_MODEL", "en-us-neutral") # Adjust based on LocalAI config

    def reduce_noise(self, audio_bytes: bytes) -> bytes:
        """
        Reduces background noise from audio bytes using noisereduce.
        Focuses on direct human voice by filtering out steady-state noise.
        """
        # Load audio with pydub
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes))
        
        # Convert to numpy array
        samples = np.array(audio_segment.get_array_of_samples())
        
        # If stereo, reduce noise on both channels or convert to mono
        if audio_segment.channels == 2:
            samples = samples.reshape((-1, 2))
            reduced_noise = nr.reduce_noise(y=samples.T, sr=audio_segment.frame_rate).T
        else:
            reduced_noise = nr.reduce_noise(y=samples, sr=audio_segment.frame_rate)

        # Convert back to audio segment
        reduced_audio = AudioSegment(
            reduced_noise.tobytes(),
            frame_rate=audio_segment.frame_rate,
            sample_width=audio_segment.sample_width,
            channels=audio_segment.channels
        )

        # Export to wav bytes
        out_io = io.BytesIO()
        reduced_audio.export(out_io, format="wav")
        return out_io.getvalue()

    def transcribe(self, audio_bytes: bytes, reduce_noise: bool = True) -> str:
        """Transcribes audio using LocalAI Whisper endpoint."""
        if reduce_noise:
            audio_bytes = self.reduce_noise(audio_bytes)

        # LocalAI expects a file object
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "input.wav"

        try:
            transcript = self.client.audio.transcriptions.create(
                model=self.whisper_model,
                file=audio_file
            )
            return transcript.text
        except Exception as e:
            print(f"[VoiceHandler] Transcription Error: {e}")
            return f"Error: {e}"

    def generate_speech(self, text: str) -> bytes:
        """Generates speech from text using LocalAI TTS endpoint."""
        try:
            response = self.client.audio.speech.create(
                model=self.tts_model,
                voice="alloy", # Adjust based on LocalAI config
                input=text
            )
            # OpenAI client returns a context manager for stream
            return response.content
        except Exception as e:
            print(f"[VoiceHandler] TTS Error: {e}")
            return b""

if __name__ == "__main__":
    # Quick test if run directly
    handler = VoiceHandler()
    print(f"Initialized with base: {handler.api_base}")
