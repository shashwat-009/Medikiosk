"""
Provider-independent interface for the TTS (Text-to-Speech) subsystem.

Mirrors ``ai/asr/base.py``: defines the contract every TTS provider must
implement, so the conversation layer depends only on ``TTSProvider`` and
``TTSResponse`` — never on a concrete provider like Edge TTS or (later)
Sarvam TTS.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai.tts.schemas import TTSRequest, TTSResponse


class TTSError(Exception):
    """Base class for all TTS-subsystem errors."""


class UnsupportedLanguageError(TTSError):
    """Raised when a request targets a language the provider cannot speak."""


class SynthesisError(TTSError):
    """Raised when a provider fails to synthesize audio (network failure,
    malformed provider response, file write failure, etc.). Provider-specific
    exceptions must be translated into this type before leaving the provider
    module, matching the pattern used by ai/asr's TranscriptionError."""


class TTSProvider(ABC):
    """
    Abstract interface every TTS provider must implement.

    Async because at least one real provider (Edge TTS) is inherently
    asynchronous; keeping the interface async lets all providers share one
    contract instead of some being sync wrappers around async code.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short, stable identifier for this provider (e.g. 'edge_tts')."""
        raise NotImplementedError

    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """
        Synthesize speech for ``request`` and return a standardized
        ``TTSResponse``.

        Raises:
            UnsupportedLanguageError: If the provider cannot speak
                ``request.language_code``.
            SynthesisError: If synthesis fails for any other reason.
        """
        raise NotImplementedError