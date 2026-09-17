"""
Public exports for the MediKiosk TTS (Text-to-Speech) package.

    Conversation / Question Generator
                ↓
            text response
                ↓
            TTS Service   (this package)
                ↓
           TTS Provider   (EdgeTTSProvider today; SarvamTTSProvider later)
                ↓
          generated audio
                ↓
            Backend → Frontend → Patient hears audio

TTS converts already-generated text into speech. It does not diagnose,
make medical decisions, modify clinical data, generate medical advice, or
detect red flags — see ai/tts/README.md for the full module scope.
"""

from ai.tts.base import SynthesisError, TTSError, TTSProvider, UnsupportedLanguageError
from ai.tts.config import TTSConfig
from ai.tts.edge_tts import EdgeTTSProvider
from ai.tts.mock_tts import MockTTSProvider
from ai.tts.schemas import (
    OutputFormat,
    SupportedLanguage,
    TTSRequest,
    TTSResponse,
    VoiceGender,
)

__all__ = [
    "EdgeTTSProvider",
    "MockTTSProvider",
    "OutputFormat",
    "SupportedLanguage",
    "SynthesisError",
    "TTSConfig",
    "TTSError",
    "TTSProvider",
    "TTSRequest",
    "TTSResponse",
    "UnsupportedLanguageError",
    "VoiceGender",
]