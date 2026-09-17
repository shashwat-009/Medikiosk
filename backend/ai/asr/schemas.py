"""
Provider-independent data contracts for the ASR (Automatic Speech Recognition)
subsystem.

This module defines the *standardized* shape of data that flows out of the
ASR module, regardless of which underlying provider (Mock, Sarvam, or any
future provider) produced it. Nothing here should ever import a
provider-specific SDK, know about HTTP, or contain provider-specific fields.

Scope reminder (ASR module boundary):
    ASR is responsible ONLY for: Audio -> Speech Recognition -> Standardized
    Transcript. It must NOT contain clinical reasoning, diagnosis, symptom
    extraction, summarization, or any other downstream concern. Those belong
    to other modules that consume ``ASRResponse``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ASRResponse(BaseModel):
    """
    Standardized result returned by ANY ASR provider.

    This is the single contract the rest of MediKiosk (e.g. the Conversation
    Module) should depend on. Provider-specific response formats (Sarvam's
    raw API payload, etc.) must be translated into this model inside the
    provider's own module and never leaked outside the ASR package.
    """

    model_config = ConfigDict(
        # Providers may return richer transcripts than plain strings can
        # normally hold (mixed scripts, punctuation, etc.) — we don't want
        # unexpected keys silently accepted, so extra fields are rejected.
        # This keeps the contract strict and predictable for downstream
        # modules and makes provider bugs fail loudly instead of leaking
        # unknown data.
        extra="forbid",
        # Once created, an ASRResponse represents a finished recognition
        # result. Making it immutable prevents accidental mutation by
        # downstream code that should only ever read it.
        frozen=True,
    )

    text: str = Field(
        ...,
        min_length=1,
        description=(
            "The recognized transcript text. Must be non-empty after "
            "whitespace is stripped; leading/trailing whitespace is "
            "normalized automatically."
        ),
    )

    language: str | None = Field(
        default=None,
        description=(
            "Language (or language/locale code, e.g. 'hi', 'en-IN') of the "
            "recognized speech, if the provider reports one. None if "
            "unknown or not returned by the provider."
        ),
    )

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Provider-reported confidence score for the transcript, "
            "expressed as a value between 0.0 and 1.0. Optional because "
            "not every ASR provider returns a confidence score."
        ),
    )

    provider: str = Field(
        ...,
        min_length=1,
        description=(
            "Identifier of the ASR provider that produced this result "
            "(e.g. 'mock', 'sarvam'). Used for logging/debugging only — "
            "downstream modules should not branch their logic on this "
            "value."
        ),
    )

    request_id: str | None = Field(
        default=None,
        description=(
            "Optional identifier correlating this response to a specific "
            "recognition request, useful for logging and troubleshooting. "
            "None if the provider does not issue one."
        ),
    )

    duration_ms: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Duration of the recognized audio in milliseconds, if known. "
            "Must be zero or positive when provided."
        ),
    )

    @field_validator("text", mode="after")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        """Strip surrounding whitespace and reject blank transcripts."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be empty or whitespace-only")
        return stripped

    @field_validator("language", "request_id", mode="after")
    @classmethod
    def _validate_optional_strings(cls, value: str | None) -> str | None:
        """Treat blank optional strings as if they were not provided."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def normalized_text(self) -> str:
        """
        Return a lightly normalized version of ``text`` for simple
        comparisons (e.g. tests or logging).

        This collapses repeated internal whitespace and lowercases the
        text. It is intentionally minimal — anything more elaborate
        (punctuation stripping, medical term normalization, etc.) belongs
        to a downstream module, not to ASR.
        """
        return " ".join(self.text.split()).lower()