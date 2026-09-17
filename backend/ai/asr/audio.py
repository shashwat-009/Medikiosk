"""
Lightweight audio validation and utility layer for the ASR subsystem.

This module sits between "a file on disk" and "an ASR provider":

    Audio file -> Validation -> ASR provider

It answers only generic questions such as "does this file exist", "is it a
file", "is the extension one we generically accept", and "is it a sane
size" — using nothing but ``pathlib`` and filesystem metadata (no audio is
ever read into memory here).

This module does NOT:
    - perform speech recognition
    - call any ASR provider (Sarvam or otherwise)
    - know provider-specific format/encoding/sample-rate requirements

Provider-specific constraints (e.g. "Sarvam only accepts 16kHz mono WAV")
belong inside the relevant provider module (e.g. ``sarvam_asr.py``), which
should perform its own additional checks/conversion *after* this module's
generic validation has passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ai.asr.base import ASRError, AudioFileNotFoundError

# ---------------------------------------------------------------------------
# Configurable defaults
# ---------------------------------------------------------------------------

#: Generic set of audio file extensions accepted into the ASR pipeline.
#: This is intentionally broad and provider-agnostic — a given provider
#: (e.g. Sarvam) may accept only a subset of these, or require additional
#: constraints (sample rate, channel count, encoding). Such constraints
#: must be enforced inside that provider's own module, not here.
DEFAULT_SUPPORTED_AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}
)

#: Default maximum accepted audio file size, in bytes (25 MB). Chosen as a
#: reasonable generic ceiling for short clinical-history voice clips; a
#: specific deployment or provider may want a stricter limit, which can be
#: supplied via ``AudioValidationConfig``.
DEFAULT_MAX_AUDIO_FILE_SIZE_BYTES: int = 25 * 1024 * 1024


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AudioValidationError(ASRError):
    """Base class for all generic audio-validation failures.

    Inherits from ``ASRError`` (defined in ``base.py``) so callers can
    catch every ASR-related failure — validation or transcription — with a
    single ``except ASRError:`` if they choose to.
    """


class NotAFileError(AudioValidationError):
    """Raised when ``audio_path`` exists but is not a regular file.

    For example, the path points to a directory or a special filesystem
    object (socket, device file, etc.).
    """


class UnsupportedAudioFormatError(AudioValidationError):
    """Raised when the file extension is not in the supported set."""


class EmptyAudioFileError(AudioValidationError):
    """Raised when the audio file exists but contains zero bytes."""


class AudioTooLargeError(AudioValidationError):
    """Raised when the audio file exceeds the configured maximum size."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AudioValidationConfig:
    """
    Generic, provider-agnostic audio validation rules.

    This intentionally does NOT express anything provider-specific (e.g.
    sample rate, channel count, codec). It only controls the checks
    performed by this module: accepted extensions and maximum file size.

    Attributes:
        supported_extensions: Lowercase file extensions (including the
            leading dot) that are generically accepted, e.g. ``".wav"``.
        max_file_size_bytes: Maximum allowed file size in bytes.
    """

    supported_extensions: frozenset[str] = field(
        default_factory=lambda: DEFAULT_SUPPORTED_AUDIO_EXTENSIONS
    )
    max_file_size_bytes: int = DEFAULT_MAX_AUDIO_FILE_SIZE_BYTES


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------


def get_audio_file_size_bytes(audio_path: Path) -> int:
    """
    Return the size of ``audio_path`` in bytes without reading its content.

    Uses filesystem metadata (``Path.stat``) only.

    Raises:
        AudioFileNotFoundError: If ``audio_path`` does not exist.
    """
    if not audio_path.exists():
        raise AudioFileNotFoundError(f"Audio file not found: {audio_path}")
    return audio_path.stat().st_size


def is_supported_audio_format(
    audio_path: Path, config: AudioValidationConfig | None = None
) -> bool:
    """
    Return whether ``audio_path``'s extension is in the supported set.

    This is a pure, non-raising convenience check (useful for building UI
    hints or quick filters) — it does not verify the file exists.
    """
    cfg = config or AudioValidationConfig()
    return audio_path.suffix.lower() in cfg.supported_extensions


def validate_audio_file(
    audio_path: Path, config: AudioValidationConfig | None = None
) -> Path:
    """
    Run generic, provider-agnostic validation on an audio file.

    Checks performed, in order:
        1. The path exists.
        2. The path points to a regular file (not a directory, etc.).
        3. The file extension is in the supported set.
        4. The file is not empty.
        5. The file does not exceed the configured maximum size.

    All checks are done via filesystem metadata only — the audio content
    itself is never loaded into memory.

    Args:
        audio_path: Path to the candidate audio file.
        config: Optional validation rules. Defaults to
            ``AudioValidationConfig()`` (the module defaults) when omitted.

    Returns:
        Path: The same ``audio_path``, once all checks pass — returned for
        convenient chaining, e.g. ``provider.transcribe(validate_audio_file(p))``.

    Raises:
        AudioFileNotFoundError: If ``audio_path`` does not exist.
        NotAFileError: If ``audio_path`` exists but is not a regular file.
        UnsupportedAudioFormatError: If the extension is not supported.
        EmptyAudioFileError: If the file is zero bytes.
        AudioTooLargeError: If the file exceeds ``config.max_file_size_bytes``.
    """
    cfg = config or AudioValidationConfig()

    if not audio_path.exists():
        raise AudioFileNotFoundError(f"Audio file not found: {audio_path}")

    if not audio_path.is_file():
        raise NotAFileError(f"Audio path is not a regular file: {audio_path}")

    extension = audio_path.suffix.lower()
    if extension not in cfg.supported_extensions:
        supported = ", ".join(sorted(cfg.supported_extensions))
        raise UnsupportedAudioFormatError(
            f"Unsupported audio format '{extension}' for {audio_path}. "
            f"Supported extensions: {supported}"
        )

    size_bytes = audio_path.stat().st_size
    if size_bytes == 0:
        raise EmptyAudioFileError(f"Audio file is empty: {audio_path}")

    if size_bytes > cfg.max_file_size_bytes:
        raise AudioTooLargeError(
            f"Audio file {audio_path} is {size_bytes} bytes, which exceeds "
            f"the maximum allowed size of {cfg.max_file_size_bytes} bytes"
        )

    return audio_path