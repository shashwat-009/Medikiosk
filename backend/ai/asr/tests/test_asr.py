"""
Test suite for the ASR (Automatic Speech Recognition) subsystem.

Covers, for the pieces implemented so far:
    - schemas.py   (ASRResponse validation rules)
    - base.py      (ASRProvider interface + exception hierarchy)
    - audio.py     (generic, provider-agnostic audio validation)
    - mock_asr.py  (MockASRProvider, the offline/deterministic provider)

Explicitly OUT of scope for this file:
    - sarvam_asr.py — the real Sarvam API integration does not exist yet,
      so there is nothing to test. No network calls, API keys, or
      environment variables are required anywhere in this suite.

All tests are fully offline and deterministic: audio "files" used here are
tiny placeholder byte strings written to a pytest-managed temporary
directory (``tmp_path``) — no real audio content or codecs are involved,
matching the ASR module's own "no real speech processing" boundary for
mock/testing purposes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai.asr.audio import (
    AudioTooLargeError,
    AudioValidationConfig,
    EmptyAudioFileError,
    NotAFileError,
    UnsupportedAudioFormatError,
    is_supported_audio_format,
    validate_audio_file,
)
from ai.asr.base import ASRError, ASRProvider, AudioFileNotFoundError
from ai.asr.mock_asr import (
    MOCK_PROVIDER_NAME,
    MockASRProvider,
    MockTranscript,
    SAMPLE_ENGLISH,
    SAMPLE_HINDI,
    SAMPLE_HINGLISH,
)
from ai.asr.schemas import ASRResponse


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_audio_file(tmp_path: Path):
    """
    Factory fixture that writes a small placeholder audio file to a pytest
    temp directory and returns its path.

    Content is never real audio — these tests only exercise filesystem
    metadata (existence, extension, size) and the deterministic mock
    provider, neither of which reads actual audio content.
    """

    def _make(name: str = "sample.wav", content: bytes = b"RIFF....WAVEfmt ") -> Path:
        path = tmp_path / name
        path.write_bytes(content)
        return path

    return _make


@pytest.fixture
def valid_audio_file(make_audio_file) -> Path:
    """A single valid, supported, non-empty audio file."""
    return make_audio_file("valid_clip.wav")


# ---------------------------------------------------------------------------
# schemas.py — ASRResponse
# ---------------------------------------------------------------------------


class TestASRResponseSchema:
    """Validation behavior of the provider-independent ASRResponse model."""

    def test_valid_asr_response_creation(self) -> None:
        """All fields populated with valid values should construct cleanly."""
        response = ASRResponse(
            text="mujhe do din se bukhar hai",
            language="hi",
            confidence=0.95,
            provider="mock",
            request_id="req-1",
            duration_ms=2500,
        )
        assert response.text == "mujhe do din se bukhar hai"
        assert response.language == "hi"
        assert response.confidence == 0.95
        assert response.provider == "mock"
        assert response.request_id == "req-1"
        assert response.duration_ms == 2500

    def test_minimal_valid_response_only_required_fields(self) -> None:
        """Optional fields (language, confidence, request_id, duration_ms)
        may all be omitted — confidence in particular must not be
        mandatory, since not every provider returns one."""
        response = ASRResponse(text="hello", provider="mock")
        assert response.language is None
        assert response.confidence is None
        assert response.request_id is None
        assert response.duration_ms is None

    @pytest.mark.parametrize("bad_confidence", [-0.01, 1.01, 2.0, -5.0])
    def test_confidence_out_of_range_rejected(self, bad_confidence: float) -> None:
        """confidence must lie within the inclusive [0.0, 1.0] range."""
        with pytest.raises(ValidationError):
            ASRResponse(text="hello", provider="mock", confidence=bad_confidence)

    @pytest.mark.parametrize("good_confidence", [0.0, 0.5, 1.0])
    def test_confidence_boundary_values_accepted(self, good_confidence: float) -> None:
        """0.0 and 1.0 are valid inclusive boundaries."""
        response = ASRResponse(
            text="hello", provider="mock", confidence=good_confidence
        )
        assert response.confidence == good_confidence

    def test_empty_text_rejected(self) -> None:
        """An empty string is not a valid transcript."""
        with pytest.raises(ValidationError):
            ASRResponse(text="", provider="mock")

    def test_whitespace_only_text_rejected(self) -> None:
        """Whitespace-only text is treated as empty and rejected."""
        with pytest.raises(ValidationError):
            ASRResponse(text="   \n\t  ", provider="mock")

    def test_text_is_stripped_of_surrounding_whitespace(self) -> None:
        """Leading/trailing whitespace around otherwise-valid text is
        normalized away rather than preserved verbatim."""
        response = ASRResponse(text="  hello world  ", provider="mock")
        assert response.text == "hello world"

    def test_missing_required_text_rejected(self) -> None:
        """`text` is required; omitting it must fail validation."""
        with pytest.raises(ValidationError):
            ASRResponse(provider="mock")  # type: ignore[call-arg]

    def test_missing_required_provider_rejected(self) -> None:
        """`provider` is required; omitting it must fail validation."""
        with pytest.raises(ValidationError):
            ASRResponse(text="hello")  # type: ignore[call-arg]

    def test_unknown_extra_fields_rejected(self) -> None:
        """Provider-specific/unexpected fields must not silently pass
        through the standardized schema (extra='forbid')."""
        with pytest.raises(ValidationError):
            ASRResponse(
                text="hello", provider="mock", sarvam_internal_field="leak"
            )  # type: ignore[call-arg]

    def test_response_is_immutable(self) -> None:
        """An ASRResponse represents a finished result and should not be
        mutable after construction."""
        response = ASRResponse(text="hello", provider="mock")
        with pytest.raises(ValidationError):
            response.text = "changed"  # type: ignore[misc]

    def test_negative_duration_rejected(self) -> None:
        """duration_ms must be zero or positive when provided."""
        with pytest.raises(ValidationError):
            ASRResponse(text="hello", provider="mock", duration_ms=-1)

    def test_normalized_text_helper(self) -> None:
        """normalized_text() collapses internal whitespace and lowercases,
        without mutating the original `text` field."""
        response = ASRResponse(text="  Mujhe   Bukhar  Hai  ", provider="mock")
        assert response.text == "Mujhe   Bukhar  Hai"
        assert response.normalized_text() == "mujhe bukhar hai"


# ---------------------------------------------------------------------------
# base.py — ASRProvider interface and exception hierarchy
# ---------------------------------------------------------------------------


class TestASRProviderInterface:
    """Structural guarantees of the abstract provider interface."""

    def test_asr_provider_cannot_be_instantiated_directly(self) -> None:
        """ASRProvider is abstract and must not be directly constructible."""
        with pytest.raises(TypeError):
            ASRProvider()  # type: ignore[abstract]

    def test_incomplete_subclass_cannot_be_instantiated(self) -> None:
        """A subclass missing a required abstract member must also fail to
        instantiate — proves the interface is actually enforced."""

        class IncompleteProvider(ASRProvider):
            @property
            def provider_name(self) -> str:
                return "incomplete"

            # transcribe() intentionally not implemented

        with pytest.raises(TypeError):
            IncompleteProvider()  # type: ignore[abstract]

    def test_audio_file_not_found_error_is_an_asr_error(self) -> None:
        """AudioFileNotFoundError must be catchable both as an ASRError and
        as a standard FileNotFoundError."""
        assert issubclass(AudioFileNotFoundError, ASRError)
        assert issubclass(AudioFileNotFoundError, FileNotFoundError)


# ---------------------------------------------------------------------------
# audio.py — generic audio validation
# ---------------------------------------------------------------------------


class TestAudioValidation:
    """Generic, provider-agnostic validation performed before any ASR
    provider ever sees the file."""

    def test_valid_audio_file_passes_and_returns_path(
        self, valid_audio_file: Path
    ) -> None:
        result = validate_audio_file(valid_audio_file)
        assert result == valid_audio_file

    def test_missing_audio_file_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.wav"
        with pytest.raises(AudioFileNotFoundError):
            validate_audio_file(missing)

    def test_directory_path_raises_not_a_file(self, tmp_path: Path) -> None:
        with pytest.raises(NotAFileError):
            validate_audio_file(tmp_path)

    def test_unsupported_extension_raises(self, make_audio_file) -> None:
        text_file = make_audio_file("notes.txt", content=b"just text")
        with pytest.raises(UnsupportedAudioFormatError):
            validate_audio_file(text_file)

    def test_empty_audio_file_raises(self, make_audio_file) -> None:
        empty_file = make_audio_file("empty.wav", content=b"")
        with pytest.raises(EmptyAudioFileError):
            validate_audio_file(empty_file)

    def test_oversized_audio_file_raises(self, make_audio_file) -> None:
        big_file = make_audio_file("big.wav", content=b"x" * 2000)
        strict_config = AudioValidationConfig(max_file_size_bytes=1000)
        with pytest.raises(AudioTooLargeError):
            validate_audio_file(big_file, config=strict_config)

    def test_custom_config_can_narrow_supported_extensions(
        self, make_audio_file
    ) -> None:
        """A provider wanting stricter formats than the generic default can
        supply its own AudioValidationConfig."""
        mp3_file = make_audio_file("clip.mp3", content=b"fake mp3 bytes")
        wav_only_config = AudioValidationConfig(
            supported_extensions=frozenset({".wav"})
        )
        with pytest.raises(UnsupportedAudioFormatError):
            validate_audio_file(mp3_file, config=wav_only_config)

    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("song.mp3", True),
            ("clip.wav", True),
            ("voice.m4a", True),
            ("document.txt", False),
            ("archive.zip", False),
        ],
    )
    def test_is_supported_audio_format(self, filename: str, expected: bool) -> None:
        assert is_supported_audio_format(Path(filename)) is expected


# ---------------------------------------------------------------------------
# mock_asr.py — MockASRProvider
# ---------------------------------------------------------------------------


class TestMockASRProvider:
    """Behavior of the deterministic, offline mock ASR provider."""

    def test_conforms_to_asr_provider_interface(self) -> None:
        """MockASRProvider must be a genuine ASRProvider, so it can stand
        in anywhere an ASRProvider is expected (e.g. SarvamASRProvider
        later)."""
        provider = MockASRProvider()
        assert isinstance(provider, ASRProvider)

    def test_provider_name_identifies_the_mock(self) -> None:
        provider = MockASRProvider()
        assert provider.provider_name == MOCK_PROVIDER_NAME
        assert provider.provider_name == "mock"

    def test_default_transcript_matches_expected_hindi_sample(
        self, valid_audio_file: Path
    ) -> None:
        """Default configuration (no explicit mapping) returns the
        canonical Hindi sample transcript."""
        provider = MockASRProvider()
        result = provider.transcribe(valid_audio_file)
        assert result.text == "mujhe do din se bukhar hai"
        assert isinstance(result, ASRResponse)
        assert result.provider == "mock"

    def test_hindi_transcript(self, make_audio_file) -> None:
        audio_path = make_audio_file("hindi_sample.wav")
        provider = MockASRProvider(
            transcripts_by_filename={"hindi_sample.wav": SAMPLE_HINDI}
        )
        result = provider.transcribe(audio_path)
        assert result.text == SAMPLE_HINDI.text
        assert result.language == "hi"

    def test_english_transcript(self, make_audio_file) -> None:
        audio_path = make_audio_file("english_sample.wav")
        provider = MockASRProvider(
            transcripts_by_filename={"english_sample.wav": SAMPLE_ENGLISH}
        )
        result = provider.transcribe(audio_path)
        assert result.text == "I have had a fever for two days"
        assert result.language == "en"

    def test_hinglish_transcript(self, make_audio_file) -> None:
        audio_path = make_audio_file("hinglish_sample.wav")
        provider = MockASRProvider(
            transcripts_by_filename={"hinglish_sample.wav": SAMPLE_HINGLISH}
        )
        result = provider.transcribe(audio_path)
        assert result.text == "mujhe do din se fever hai aur sar dard bhi ho raha hai"
        assert result.language == "hi-en"

    def test_unmapped_filename_falls_back_to_default(
        self, make_audio_file
    ) -> None:
        audio_path = make_audio_file("unrecognized.wav")
        custom_default = MockTranscript(text="fallback transcript")
        provider = MockASRProvider(default_transcript=custom_default)
        result = provider.transcribe(audio_path)
        assert result.text == "fallback transcript"

    def test_missing_audio_path_raises_by_default(self, tmp_path: Path) -> None:
        """With require_file_exists=True (the default), a nonexistent path
        must raise the same AudioFileNotFoundError a real provider would
        raise."""
        provider = MockASRProvider()
        missing_path = tmp_path / "ghost.wav"
        with pytest.raises(AudioFileNotFoundError):
            provider.transcribe(missing_path)

    def test_require_file_exists_false_allows_missing_path(self) -> None:
        """Opting out of the existence check supports pure logic-only unit
        tests that don't want to manage real temp files."""
        provider = MockASRProvider(require_file_exists=False)
        result = provider.transcribe(Path("/nonexistent/clip.wav"))
        assert result.text == "mujhe do din se bukhar hai"

    def test_deterministic_across_repeated_calls(
        self, valid_audio_file: Path
    ) -> None:
        """The same input must always produce an identical result — no
        hidden state or randomness."""
        provider = MockASRProvider()
        first = provider.transcribe(valid_audio_file)
        second = provider.transcribe(valid_audio_file)
        assert first == second

    def test_returns_asr_response_instance(self, valid_audio_file: Path) -> None:
        """The provider must return the standardized ASRResponse type, not
        a raw dict or a provider-specific object."""
        provider = MockASRProvider()
        result = provider.transcribe(valid_audio_file)
        assert isinstance(result, ASRResponse)