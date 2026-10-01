"""
Deterministic Mock TTS provider for local development and testing.

Lets the rest of MediSetu be built and tested without any network access
or real audio synthesis, mirroring ``ai/asr/mock_asr.py``'s role for ASR.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from ai.tts.base import TTSProvider
from ai.tts.config import TTSConfig
from ai.tts.schemas import SupportedLanguage, TTSRequest, TTSResponse

#: Identifier used to populate TTSResponse.provider for this provider.
MOCK_PROVIDER_NAME = "mock"

#: Deterministic placeholder "voice" names per language, distinct from any
#: real Edge TTS voice name so tests can never confuse mock output for
#: real provider output.
_MOCK_VOICES: dict[SupportedLanguage, str] = {
    SupportedLanguage.HINDI: "mock-hi-voice",
    SupportedLanguage.ENGLISH: "mock-en-voice",
    SupportedLanguage.MARATHI: "mock-mr-voice",
    SupportedLanguage.BENGALI: "mock-bn-voice",
}


class MockTTSProvider(TTSProvider):
    """
    Offline TTSProvider that writes a small placeholder audio file instead
    of performing real synthesis.

    Useful for testing request validation, provider-interface conformance,
    voice selection, and response-schema shape without any network access.
    """

    def __init__(self, config: TTSConfig | None = None) -> None:
        self._config = config or TTSConfig()

    @property
    def provider_name(self) -> str:
        return MOCK_PROVIDER_NAME

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """Write a tiny deterministic placeholder file and return a valid
        TTSResponse. No network access, no real audio is generated."""
        self._config.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"mock_{uuid.uuid4().hex}.{request.output_format.value}"
        audio_path = self._config.output_dir / filename
        audio_path.write_bytes(b"MOCK_AUDIO_PLACEHOLDER")

        voice = request.voice or _MOCK_VOICES[request.language_code]

        return TTSResponse(
            audio_path=audio_path,
            language_code=request.language_code,
            voice=voice,
            provider=self.provider_name,
            output_format=request.output_format,
            duration_ms=0,
        )