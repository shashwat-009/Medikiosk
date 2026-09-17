"""
Edge TTS provider implementation.

Wraps the ``edge-tts`` Python package (a community client for Microsoft
Edge's neural TTS voices) behind the standardized ``TTSProvider``
interface.

IMPORTANT LIMITATION (see ai/tts/README.md for full detail):
    edge-tts is an unofficial, internet-dependent client library. It is
    not backed by a documented, stable public API contract from
    Microsoft — it works by replicating what the Edge browser's "Read
    Aloud" feature does internally. Treat this provider as a prototype
    option, not a permanent production dependency.

Voice mapping verified against edge-tts's actual published voice list at
implementation time (see README.md):
    hi-IN: hi-IN-SwaraNeural (F) / hi-IN-MadhurNeural (M)
    en-IN: en-IN-NeerjaNeural (F) / en-IN-PrabhatNeural (M)
    mr-IN: mr-IN-AarohiNeural (F) / mr-IN-ManoharNeural (M)
    bn-IN: bn-IN-TanishaaNeural (F) / bn-IN-BashkarNeural (M)

This module does NOT expose any API key (edge-tts needs none) and does
NOT perform any clinical/dialogue logic — it only converts text to audio.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable, Final

from edge_tts import Communicate

from ai.tts.base import SynthesisError, TTSProvider, UnsupportedLanguageError
from ai.tts.config import TTSConfig
from ai.tts.schemas import SupportedLanguage, TTSRequest, TTSResponse, VoiceGender

#: Identifier used to populate TTSResponse.provider for this provider.
EDGE_TTS_PROVIDER_NAME: Final[str] = "edge_tts"

#: Centralized language -> voice mapping. Kept in ONE place (here) so it
#: never needs to be scattered through the codebase, and so a future
#: SarvamTTSProvider can define its own completely separate mapping
#: without touching this one.
#:
#: Every one of these Indian-locale voices is directly supported by
#: edge-tts's own voice list (verified, see module docstring) — no
#: fallback to a non-Indian voice was needed for any of the four
#: required languages.
LANGUAGE_VOICE_MAP: dict[SupportedLanguage, dict[VoiceGender, str]] = {
    SupportedLanguage.HINDI: {
        VoiceGender.FEMALE: "hi-IN-SwaraNeural",
        VoiceGender.MALE: "hi-IN-MadhurNeural",
    },
    SupportedLanguage.ENGLISH: {
        VoiceGender.FEMALE: "en-IN-NeerjaNeural",
        VoiceGender.MALE: "en-IN-PrabhatNeural",
    },
    SupportedLanguage.MARATHI: {
        VoiceGender.FEMALE: "mr-IN-AarohiNeural",
        VoiceGender.MALE: "mr-IN-ManoharNeural",
    },
    SupportedLanguage.BENGALI: {
        VoiceGender.FEMALE: "bn-IN-TanishaaNeural",
        VoiceGender.MALE: "bn-IN-BashkarNeural",
    },
}

#: Gender used when a request specifies neither an explicit voice nor a
#: gender preference.
_DEFAULT_GENDER: Final[VoiceGender] = VoiceGender.FEMALE

#: Type of the callable used to construct a Communicate-like object.
#: Overridable in the constructor purely for offline unit testing (no
#: real network object is created when a fake factory is injected).
CommunicateFactory = Callable[..., Any]


def resolve_voice(request: TTSRequest) -> str:
    """
    Determine which Edge TTS voice identifier to use for ``request``.

    An explicit ``request.voice`` always wins. Otherwise the voice is
    looked up from ``LANGUAGE_VOICE_MAP`` using ``request.language_code``
    and ``request.gender`` (defaulting to FEMALE).

    Raises:
        UnsupportedLanguageError: If ``request.language_code`` has no
            entry in ``LANGUAGE_VOICE_MAP``.
    """
    if request.voice:
        return request.voice

    voices_for_language = LANGUAGE_VOICE_MAP.get(request.language_code)
    if voices_for_language is None:
        supported = sorted(lang.value for lang in LANGUAGE_VOICE_MAP)
        raise UnsupportedLanguageError(
            f"Edge TTS provider has no voice mapping for language "
            f"'{request.language_code.value}'. Supported: {supported}"
        )

    gender = request.gender or _DEFAULT_GENDER
    return voices_for_language[gender]


class EdgeTTSProvider(TTSProvider):
    """
    ``TTSProvider`` implementation backed by the real ``edge-tts`` package.

    Requires no API key. Requires internet access to reach Microsoft's
    Edge speech service.
    """

    def __init__(
        self,
        config: TTSConfig | None = None,
        communicate_factory: CommunicateFactory = Communicate,
    ) -> None:
        """
        Args:
            config: Output directory / format configuration. Defaults to
                ``TTSConfig()``.
            communicate_factory: Callable used to construct the
                edge-tts ``Communicate``-like object, called as
                ``communicate_factory(text, voice)``. Defaults to the
                real ``edge_tts.Communicate`` class. Overriding this is
                the seam used for offline unit testing — a fake factory
                can be injected so no real network call is made.
        """
        self._config = config or TTSConfig()
        self._communicate_factory = communicate_factory

    @property
    def provider_name(self) -> str:
        return EDGE_TTS_PROVIDER_NAME

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """
        Synthesize ``request`` via Edge TTS and save the result as an MP3.

        Raises:
            UnsupportedLanguageError: If no voice mapping exists for
                ``request.language_code``.
            SynthesisError: If Edge TTS fails at the network/protocol
                level, or if writing the output file fails.
        """
        voice = resolve_voice(request)

        self._config.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"edge_{uuid.uuid4().hex}.{request.output_format.value}"
        audio_path = self._config.output_dir / filename

        try:
            communicate = self._communicate_factory(request.text, voice=voice)
            await communicate.save(str(audio_path))
        except UnsupportedLanguageError:
            raise
        except Exception as exc:  # noqa: BLE001 - deliberately broad: translate
            # ANY edge-tts/network/protocol failure into our own exception
            # type, so provider-specific exceptions never leak outward.
            raise SynthesisError(
                f"Edge TTS synthesis failed for language "
                f"'{request.language_code.value}': {exc}"
            ) from exc

        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise SynthesisError(
                f"Edge TTS reported success but no audio was written to {audio_path}"
            )

        return TTSResponse(
            audio_path=audio_path,
            language_code=request.language_code,
            voice=voice,
            provider=self.provider_name,
            output_format=request.output_format,
        )