"""
Provider-independent data contracts for the TTS (Text-to-Speech) subsystem.

Mirrors the design philosophy of ``ai/asr/schemas.py``: a single
standardized response type that every provider (Edge TTS today, Sarvam
TTS later) must produce, so the rest of MediKiosk never needs to know
which provider generated a given audio file.

This module does NOT perform synthesis, does NOT call any provider, and
does NOT know about Edge TTS or Sarvam specifically.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SupportedLanguage(str, Enum):
    """Languages MediKiosk's TTS layer supports, by BCP-47 locale code."""

    HINDI = "hi-IN"
    ENGLISH = "en-IN"
    MARATHI = "mr-IN"
    BENGALI = "bn-IN"


class VoiceGender(str, Enum):
    """Optional voice-gender preference, used only when ``voice`` is not
    explicitly specified on a TTSRequest."""

    MALE = "male"
    FEMALE = "female"


class OutputFormat(str, Enum):
    """Audio output container/codec. Only MP3 is used today, but this is
    kept as an enum so a provider can support more formats later without
    changing the schema's shape."""

    MP3 = "mp3"


class TTSRequest(BaseModel):
    """
    A standardized request to synthesize speech from text.

    ``voice`` is an explicit provider-recognized voice identifier
    (optional escape hatch); when omitted, a provider selects its own
    default voice for ``language_code`` (and ``gender``, if given).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(
        ...,
        min_length=1,
        description="Text to synthesize. Must be non-empty after whitespace is stripped.",
    )
    language_code: SupportedLanguage = Field(
        ..., description="Target language/locale for synthesis."
    )
    voice: str | None = Field(
        default=None,
        description=(
            "Explicit provider voice identifier (e.g. 'hi-IN-SwaraNeural'). "
            "If omitted, the provider chooses its own default voice for "
            "language_code (and gender, if given)."
        ),
    )
    gender: VoiceGender | None = Field(
        default=None,
        description="Optional voice-gender preference, used only when voice is omitted.",
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.MP3, description="Desired audio output format."
    )

    @field_validator("text", mode="after")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be empty or whitespace-only")
        return stripped


class TTSResponse(BaseModel):
    """
    Standardized result returned by ANY TTS provider.

    Provider-specific details (raw SDK objects, websocket internals, etc.)
    must never appear here — only this fixed, provider-independent shape.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    audio_path: Path = Field(..., description="Filesystem path to the generated audio file.")
    language_code: SupportedLanguage = Field(..., description="Language the audio was synthesized in.")
    voice: str = Field(..., min_length=1, description="Provider voice identifier actually used.")
    provider: str = Field(..., min_length=1, description="Identifier of the TTS provider (e.g. 'edge_tts', 'mock').")
    output_format: OutputFormat = Field(..., description="Audio output format actually produced.")
    duration_ms: int | None = Field(
        default=None, ge=0, description="Approximate audio duration in milliseconds, if known."
    )
    request_id: str | None = Field(
        default=None, description="Optional identifier correlating this response to its request."
    )