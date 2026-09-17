"""
Provider-independent interface for the ASR (Automatic Speech Recognition)
subsystem.

This module defines the contract that every ASR provider (Mock, Sarvam, or
any future provider) must implement. Nothing here knows about a specific
provider, performs HTTP calls, or contains clinical logic — it only
describes the shape of "give me audio, get back a standardized transcript".

Scope reminder (ASR module boundary):
    This interface is responsible ONLY for describing:
        Audio -> Speech Recognition -> Standardized Transcript
    It must NOT perform clinical reasoning, diagnosis, symptom extraction,
    summarization, or database/API operations. Those belong to other
    modules that consume ``ASRResponse``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ai.asr.schemas import ASRResponse


class ASRError(Exception):
    """Base class for all ASR-subsystem errors.

    Downstream code should be able to catch this single exception type to
    handle any ASR failure, regardless of which provider raised it.
    """


class AudioFileNotFoundError(ASRError, FileNotFoundError):
    """Raised when the audio file at the given path does not exist.

    Inherits from both ``ASRError`` (so ASR-aware callers can catch it
    generically) and the standard library's ``FileNotFoundError`` (so
    generic file-handling code still recognizes it).
    """


class TranscriptionError(ASRError):
    """Raised when a provider fails to produce a transcript.

    Providers should catch their own provider-specific failures (e.g. an
    HTTP error, a malformed API response, a decoding error) and re-raise
    them as a ``TranscriptionError`` so that provider-specific details
    never leak outside the ASR module. The original exception should be
    chained via ``raise TranscriptionError(...) from original_exception``
    for debuggability.
    """


class ASRProvider(ABC):
    """
    Abstract interface that every ASR provider must implement.

    This is the single seam that keeps the ASR subsystem swappable:
    the Conversation Module (and anything else downstream) should depend
    only on this interface and on ``ASRResponse``, never on a concrete
    provider class. Swapping ``MockASRProvider`` for ``SarvamASRProvider``
    (or any future provider) should require no changes outside the ASR
    module.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        A short, stable identifier for this provider (e.g. ``"mock"`` or
        ``"sarvam"``).

        Implementations should return a constant value. This is used to
        populate ``ASRResponse.provider`` consistently and for logging —
        it is not meant to carry any provider-specific behavior.
        """
        raise NotImplementedError

    @abstractmethod
    def transcribe(self, audio_path: Path) -> ASRResponse:
        """
        Transcribe the audio file at ``audio_path`` into a standardized
        ``ASRResponse``.

        Args:
            audio_path: Path to a local audio file to transcribe. Audio
                validation (format, size, existence, etc.) is expected to
                have already happened upstream (see the Audio Validation
                stage); implementations may still raise
                ``AudioFileNotFoundError`` defensively if the path does
                not exist.

        Returns:
            ASRResponse: The standardized transcription result.

        Raises:
            AudioFileNotFoundError: If ``audio_path`` does not point to an
                existing file.
            TranscriptionError: If recognition fails for any other reason
                (provider error, network failure, malformed response,
                etc.). Provider-specific exceptions must be translated
                into this type rather than propagated directly.
        """
        raise NotImplementedError