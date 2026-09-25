"""
TTS-related configuration.

Follows the same plain, frozen-dataclass convention already used for
generic configuration in ``ai/asr/audio.py`` (``AudioValidationConfig``).
No environment variables are introduced here — callers who need different
behavior simply construct a ``TTSConfig`` with different arguments.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ai.tts.schemas import OutputFormat

#: Default provider identifier used when none is explicitly selected by
#: the caller (see ai/tts/__init__.py for how a provider is constructed).
DEFAULT_PROVIDER_NAME: str = "edge_tts"

#: Default output format for generated audio.
DEFAULT_OUTPUT_FORMAT: OutputFormat = OutputFormat.MP3


def _default_output_dir() -> Path:
    """Default location for generated audio: a dedicated subfolder under
    the system temp directory, so nothing is written inside the repo by
    default and no environment variable is required."""
    return Path(tempfile.gettempdir()) / "medisetu_tts"


@dataclass(frozen=True)
class TTSConfig:
    """
    Generic, provider-agnostic TTS configuration.

    Attributes:
        default_provider: Identifier of the provider to use when the
            caller doesn't explicitly choose one.
        output_dir: Directory generated audio files are written into.
            Created on first use if it doesn't already exist.
        default_output_format: Output format used when a request doesn't
            specify one (also the schema-level default on TTSRequest).
    """

    default_provider: str = DEFAULT_PROVIDER_NAME
    output_dir: Path = field(default_factory=_default_output_dir)
    default_output_format: OutputFormat = DEFAULT_OUTPUT_FORMAT