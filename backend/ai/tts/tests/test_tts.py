"""
Test suite for the TTS (Text-to-Speech) subsystem.

Covers: schemas.py, base.py, config.py, mock_tts.py, and edge_tts.py's
voice-selection/error-handling logic.

ALL tests in this file run fully offline:
    - MockTTSProvider never touches the network.
    - EdgeTTSProvider is tested with a FAKE communicate_factory injected
      (dependency injection), so no real call to Microsoft's Edge speech
      service is ever made here.

A real, network-dependent Edge TTS smoke test exists separately in
``ai/tts/run_tts.py`` (a manual demo script, not part of this suite).
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai.tts.base import SynthesisError, TTSError, TTSProvider, UnsupportedLanguageError
from ai.tts.config import TTSConfig
from ai.tts.edge_tts import EdgeTTSProvider, LANGUAGE_VOICE_MAP, resolve_voice
from ai.tts.mock_tts import MockTTSProvider
from ai.tts.schemas import (
    OutputFormat,
    SupportedLanguage,
    TTSRequest,
    TTSResponse,
    VoiceGender,
)


def run(coro):
    """Run an async coroutine from a plain sync pytest test, without
    adding a pytest-asyncio dependency."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_config(tmp_path: Path) -> TTSConfig:
    """A TTSConfig writing into pytest's isolated tmp_path."""
    return TTSConfig(output_dir=tmp_path / "tts_out")


@pytest.fixture
def mock_provider(tmp_config: TTSConfig) -> MockTTSProvider:
    return MockTTSProvider(config=tmp_config)


class FakeCommunicate:
    """Stand-in for edge_tts.Communicate — records its arguments and
    writes a placeholder file instead of calling the network."""

    def __init__(self, text: str, voice: str) -> None:
        self.text = text
        self.voice = voice

    async def save(self, path: str) -> None:
        Path(path).write_bytes(b"FAKE_MP3_BYTES")


class FailingCommunicate:
    """Stand-in that simulates a network/protocol failure."""

    def __init__(self, text: str, voice: str) -> None:
        pass

    async def save(self, path: str) -> None:
        raise ConnectionError("simulated network failure")


@pytest.fixture
def fake_edge_provider(tmp_config: TTSConfig) -> EdgeTTSProvider:
    return EdgeTTSProvider(config=tmp_config, communicate_factory=FakeCommunicate)


@pytest.fixture
def failing_edge_provider(tmp_config: TTSConfig) -> EdgeTTSProvider:
    return EdgeTTSProvider(config=tmp_config, communicate_factory=FailingCommunicate)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestTTSRequestSchema:
    def test_valid_request(self) -> None:
        req = TTSRequest(text="Hello", language_code=SupportedLanguage.ENGLISH)
        assert req.text == "Hello"
        assert req.output_format == OutputFormat.MP3

    def test_empty_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TTSRequest(text="", language_code=SupportedLanguage.ENGLISH)

    def test_whitespace_only_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TTSRequest(text="   ", language_code=SupportedLanguage.ENGLISH)

    def test_unsupported_language_rejected_at_schema_level(self) -> None:
        with pytest.raises(ValidationError):
            TTSRequest(text="Hello", language_code="fr-FR")  # type: ignore[arg-type]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TTSRequest(
                text="Hello", language_code=SupportedLanguage.ENGLISH, unexpected="x"
            )  # type: ignore[call-arg]

    def test_frozen_immutable(self) -> None:
        req = TTSRequest(text="Hello", language_code=SupportedLanguage.ENGLISH)
        with pytest.raises(ValidationError):
            req.text = "Changed"  # type: ignore[misc]


class TestTTSResponseSchema:
    def test_valid_response(self, tmp_path: Path) -> None:
        audio_file = tmp_path / "out.mp3"
        audio_file.write_bytes(b"data")
        resp = TTSResponse(
            audio_path=audio_file,
            language_code=SupportedLanguage.HINDI,
            voice="hi-IN-SwaraNeural",
            provider="edge_tts",
            output_format=OutputFormat.MP3,
        )
        assert resp.audio_path == audio_file
        assert resp.provider == "edge_tts"

    def test_extra_fields_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError):
            TTSResponse(
                audio_path=tmp_path / "out.mp3",
                language_code=SupportedLanguage.HINDI,
                voice="v",
                provider="edge_tts",
                output_format=OutputFormat.MP3,
                unexpected="x",
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# base.py — interface conformance
# ---------------------------------------------------------------------------


class TestTTSProviderInterface:
    def test_cannot_instantiate_abstract_provider(self) -> None:
        with pytest.raises(TypeError):
            TTSProvider()  # type: ignore[abstract]

    def test_mock_provider_conforms_to_interface(self, mock_provider: MockTTSProvider) -> None:
        assert isinstance(mock_provider, TTSProvider)

    def test_edge_provider_conforms_to_interface(self, fake_edge_provider: EdgeTTSProvider) -> None:
        assert isinstance(fake_edge_provider, TTSProvider)

    def test_synthesis_error_is_a_tts_error(self) -> None:
        assert issubclass(SynthesisError, TTSError)

    def test_unsupported_language_error_is_a_tts_error(self) -> None:
        assert issubclass(UnsupportedLanguageError, TTSError)


# ---------------------------------------------------------------------------
# Voice mapping (edge_tts.py)
# ---------------------------------------------------------------------------


class TestVoiceMapping:
    @pytest.mark.parametrize(
        "language",
        [
            SupportedLanguage.HINDI,
            SupportedLanguage.ENGLISH,
            SupportedLanguage.MARATHI,
            SupportedLanguage.BENGALI,
        ],
    )
    def test_every_supported_language_has_a_voice_mapping(
        self, language: SupportedLanguage
    ) -> None:
        assert language in LANGUAGE_VOICE_MAP
        assert VoiceGender.FEMALE in LANGUAGE_VOICE_MAP[language]
        assert VoiceGender.MALE in LANGUAGE_VOICE_MAP[language]

    def test_resolve_voice_defaults_to_female(self) -> None:
        req = TTSRequest(text="Hi", language_code=SupportedLanguage.HINDI)
        assert resolve_voice(req) == "hi-IN-SwaraNeural"

    def test_resolve_voice_respects_gender(self) -> None:
        req = TTSRequest(
            text="Hi", language_code=SupportedLanguage.HINDI, gender=VoiceGender.MALE
        )
        assert resolve_voice(req) == "hi-IN-MadhurNeural"

    def test_resolve_voice_respects_explicit_voice_override(self) -> None:
        req = TTSRequest(
            text="Hi",
            language_code=SupportedLanguage.HINDI,
            voice="hi-IN-CustomNeural",
        )
        assert resolve_voice(req) == "hi-IN-CustomNeural"

    def test_voice_names_are_distinct_per_language(self) -> None:
        all_voices = [
            voice
            for voices_by_gender in LANGUAGE_VOICE_MAP.values()
            for voice in voices_by_gender.values()
        ]
        assert len(all_voices) == len(set(all_voices))


# ---------------------------------------------------------------------------
# MockTTSProvider
# ---------------------------------------------------------------------------


class TestMockTTSProvider:
    def test_hindi_request(self, mock_provider: MockTTSProvider) -> None:
        req = TTSRequest(text="Namaste", language_code=SupportedLanguage.HINDI)
        resp = run(mock_provider.synthesize(req))
        assert resp.language_code == SupportedLanguage.HINDI
        assert resp.provider == "mock"
        assert resp.audio_path.exists()

    def test_english_request(self, mock_provider: MockTTSProvider) -> None:
        req = TTSRequest(text="Hello", language_code=SupportedLanguage.ENGLISH)
        resp = run(mock_provider.synthesize(req))
        assert resp.language_code == SupportedLanguage.ENGLISH
        assert resp.audio_path.exists()

    def test_marathi_request(self, mock_provider: MockTTSProvider) -> None:
        req = TTSRequest(text="Namaskar", language_code=SupportedLanguage.MARATHI)
        resp = run(mock_provider.synthesize(req))
        assert resp.language_code == SupportedLanguage.MARATHI
        assert resp.audio_path.exists()

    def test_bengali_request(self, mock_provider: MockTTSProvider) -> None:
        req = TTSRequest(text="Nomoshkar", language_code=SupportedLanguage.BENGALI)
        resp = run(mock_provider.synthesize(req))
        assert resp.language_code == SupportedLanguage.BENGALI
        assert resp.audio_path.exists()

    def test_provider_interface_and_response_structure(
        self, mock_provider: MockTTSProvider
    ) -> None:
        req = TTSRequest(text="Test", language_code=SupportedLanguage.ENGLISH)
        resp = run(mock_provider.synthesize(req))
        assert isinstance(resp, TTSResponse)
        assert resp.voice
        assert resp.output_format == OutputFormat.MP3

    def test_output_path_written_under_configured_output_dir(
        self, mock_provider: MockTTSProvider, tmp_config: TTSConfig
    ) -> None:
        req = TTSRequest(text="Test", language_code=SupportedLanguage.ENGLISH)
        resp = run(mock_provider.synthesize(req))
        assert resp.audio_path.parent == tmp_config.output_dir

    def test_no_network_required(self, mock_provider: MockTTSProvider) -> None:
        """Sanity check: MockTTSProvider has no import of any network
        library, so this test (and everything above) is guaranteed offline."""
        import ai.tts.mock_tts as mock_mod

        source = inspect.getsource(mock_mod)
        assert "import aiohttp" not in source
        assert "import requests" not in source
        assert "import socket" not in source


# ---------------------------------------------------------------------------
# EdgeTTSProvider (offline, via injected fake communicate_factory)
# ---------------------------------------------------------------------------


class TestEdgeTTSProviderOffline:
    def test_successful_synthesis_with_fake_factory(
        self, fake_edge_provider: EdgeTTSProvider
    ) -> None:
        req = TTSRequest(text="Hello", language_code=SupportedLanguage.ENGLISH)
        resp = run(fake_edge_provider.synthesize(req))
        assert resp.provider == "edge_tts"
        assert resp.voice == "en-IN-NeerjaNeural"
        assert resp.audio_path.exists()
        assert resp.audio_path.read_bytes() == b"FAKE_MP3_BYTES"

    def test_network_failure_translated_to_synthesis_error(
        self, failing_edge_provider: EdgeTTSProvider
    ) -> None:
        req = TTSRequest(text="Hello", language_code=SupportedLanguage.ENGLISH)
        with pytest.raises(SynthesisError):
            run(failing_edge_provider.synthesize(req))

    def test_resolve_voice_raises_for_unmapped_language(self) -> None:
        """Direct test of the provider-level language guard: build a
        request/mapping situation where the language has no voice entry
        and confirm UnsupportedLanguageError is raised, independent of
        any network call."""
        req = TTSRequest(text="Hello", language_code=SupportedLanguage.HINDI)
        original = LANGUAGE_VOICE_MAP.pop(SupportedLanguage.HINDI)
        try:
            with pytest.raises(UnsupportedLanguageError):
                resolve_voice(req)
        finally:
            LANGUAGE_VOICE_MAP[SupportedLanguage.HINDI] = original

    def test_default_voice_selection_per_language(self, fake_edge_provider: EdgeTTSProvider) -> None:
        req = TTSRequest(text="Namaskar", language_code=SupportedLanguage.MARATHI)
        resp = run(fake_edge_provider.synthesize(req))
        assert resp.voice == "mr-IN-AarohiNeural"

    def test_explicit_gender_selection(self, fake_edge_provider: EdgeTTSProvider) -> None:
        req = TTSRequest(
            text="Nomoshkar",
            language_code=SupportedLanguage.BENGALI,
            gender=VoiceGender.MALE,
        )
        resp = run(fake_edge_provider.synthesize(req))
        assert resp.voice == "bn-IN-BashkarNeural"

    def test_no_real_network_call_made(self, fake_edge_provider: EdgeTTSProvider) -> None:
        """Confirms the injected FakeCommunicate was actually used (not the
        real edge_tts.Communicate), proving this test made zero network calls."""
        req = TTSRequest(text="Hello", language_code=SupportedLanguage.ENGLISH)
        resp = run(fake_edge_provider.synthesize(req))
        # The real edge-tts package would produce a much larger, real MP3;
        # our fake always writes this exact placeholder payload.
        assert resp.audio_path.read_bytes() == b"FAKE_MP3_BYTES"


# ---------------------------------------------------------------------------
# Determinism / independence
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_mock_provider_deterministic_language_and_voice(
        self, mock_provider: MockTTSProvider
    ) -> None:
        req = TTSRequest(text="Same text", language_code=SupportedLanguage.HINDI)
        resp1 = run(mock_provider.synthesize(req))
        resp2 = run(mock_provider.synthesize(req))
        assert resp1.language_code == resp2.language_code == SupportedLanguage.HINDI
        assert resp1.voice == resp2.voice

    def test_config_defaults_are_deterministic(self) -> None:
        config1 = TTSConfig()
        config2 = TTSConfig()
        assert config1.default_provider == config2.default_provider
        assert config1.output_dir == config2.output_dir