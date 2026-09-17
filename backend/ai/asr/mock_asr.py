"""
Deterministic Mock ASR provider for local development and testing.

This provider lets the rest of MediKiosk (the Conversation Module, tests,
demos) be built and exercised WITHOUT:
    - a Sarvam API key
    - an internet connection
    - any real speech processing

It implements the same ``ASRProvider`` interface (see ``base.py``) as any
real provider (e.g. ``SarvamASRProvider``), so consumer code never needs to
know or care whether it's talking to the mock or the real thing.

This module does NOT:
    - perform any actual speech recognition
    - perform clinical extraction, symptom detection, or diagnosis
    - do adaptive/follow-up questioning
    - make network requests of any kind

It simply returns pre-configured, deterministic transcripts so that
downstream modules have something realistic and repeatable to work against.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ai.asr.base import ASRProvider, AudioFileNotFoundError
from ai.asr.schemas import ASRResponse

#: Identifier used to populate ``ASRResponse.provider`` for this provider.
#: Deliberately explicit so it's obvious in logs/tests that a result did
#: NOT come from a real ASR engine.
MOCK_PROVIDER_NAME = "mock"


@dataclass(frozen=True)
class MockTranscript:
    """
    A single canned transcription result the mock provider can return.

    This is a plain, provider-internal configuration object — it is
    converted into an ``ASRResponse`` at transcription time, it is never
    returned directly to callers.
    """

    text: str
    language: str | None = None
    confidence: float | None = None
    duration_ms: int | None = None


# ---------------------------------------------------------------------------
# Ready-made sample transcripts covering Hindi, English, and Hinglish, so
# tests/demos can pick a realistic example without writing their own.
# ---------------------------------------------------------------------------

SAMPLE_HINDI = MockTranscript(
    text="mujhe do din se bukhar hai",
    language="hi",
    confidence=0.95,
    duration_ms=2500,
)

SAMPLE_ENGLISH = MockTranscript(
    text="I have had a fever for two days",
    language="en",
    confidence=0.97,
    duration_ms=2800,
)

SAMPLE_HINGLISH = MockTranscript(
    text="mujhe do din se fever hai aur sar dard bhi ho raha hai",
    language="hi-en",
    confidence=0.90,
    duration_ms=3200,
)


class MockASRProvider(ASRProvider):
    """
    Deterministic, offline implementation of ``ASRProvider``.

    Behavior is entirely configuration-driven:
        - A transcript can be assigned to a specific audio filename via
          ``transcripts_by_filename``.
        - Any audio file whose filename is not explicitly configured falls
          back to ``default_transcript``.

    This keeps the mock trivially predictable for unit tests: the same
    input always produces the same output, with no hidden state or
    randomness.

    Example:
        >>> provider = MockASRProvider()
        >>> result = provider.transcribe(Path("any_clip.wav"))
        >>> result.text
        'mujhe do din se bukhar hai'
    """

    def __init__(
        self,
        transcripts_by_filename: Mapping[str, MockTranscript] | None = None,
        default_transcript: MockTranscript = SAMPLE_HINDI,
        require_file_exists: bool = True,
    ) -> None:
        """
        Args:
            transcripts_by_filename: Optional mapping of audio *filename*
                (``Path.name``, e.g. ``"clip.wav"``) to the
                ``MockTranscript`` that should be returned for it. Keying
                by filename (rather than a full path) keeps tests simple —
                a test can use any temp directory as long as the filename
                matches. If omitted, every input falls back to
                ``default_transcript``.
            default_transcript: The transcript returned for any audio file
                not present in ``transcripts_by_filename``. Defaults to
                ``SAMPLE_HINDI``.
            require_file_exists: If True (default), ``transcribe`` raises
                ``AudioFileNotFoundError`` when ``audio_path`` does not
                exist, matching the behavior expected of a real provider.
                Set to False for pure unit tests that only care about the
                mock's mapping logic and don't want to create dummy files.
        """
        self._transcripts_by_filename: dict[str, MockTranscript] = dict(
            transcripts_by_filename or {}
        )
        self._default_transcript = default_transcript
        self._require_file_exists = require_file_exists

    @property
    def provider_name(self) -> str:
        """Return the constant identifier for this provider: ``"mock"``."""
        return MOCK_PROVIDER_NAME

    def transcribe(self, audio_path: Path) -> ASRResponse:
        """
        Return a deterministic, pre-configured ``ASRResponse``.

        No audio is actually read or processed. The result is chosen
        purely by looking up ``audio_path.name`` in the configured
        mapping, falling back to ``default_transcript`` if there is no
        match.

        Raises:
            AudioFileNotFoundError: If ``require_file_exists`` is True
                (the default) and ``audio_path`` does not exist.
        """
        if self._require_file_exists and not audio_path.exists():
            raise AudioFileNotFoundError(f"Audio file not found: {audio_path}")

        transcript = self._transcripts_by_filename.get(
            audio_path.name, self._default_transcript
        )

        return ASRResponse(
            text=transcript.text,
            language=transcript.language,
            confidence=transcript.confidence,
            provider=self.provider_name,
            duration_ms=transcript.duration_ms,
        )