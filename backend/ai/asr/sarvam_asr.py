"""Sarvam AI implementation of the MediKiosk ASR provider contract.

This module sends one local audio file to Sarvam's synchronous Speech-to-Text
REST endpoint and translates its response into the provider-independent
``ASRResponse`` model. It contains no clinical or conversation logic.
"""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from ai.asr.base import ASRProvider, AudioFileNotFoundError, TranscriptionError
from ai.asr.config import load_project_environment
from ai.asr.schemas import ASRResponse

SARVAM_PROVIDER_NAME = "sarvam"
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
DEFAULT_SARVAM_MODEL = "saaras:v3"
DEFAULT_SARVAM_MODE = "transcribe"


class SarvamASRProvider(ASRProvider):
    """Transcribe short audio files through Sarvam's REST STT API.

    The API key is read from ``SARVAM_API_KEY`` unless supplied explicitly.
    Sarvam's REST endpoint is intended for audio shorter than 30 seconds; use
    Sarvam's batch API outside this provider for longer recordings.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = DEFAULT_SARVAM_MODEL,
        mode: str = DEFAULT_SARVAM_MODE,
        language_code: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        """Configure the documented Sarvam API request fields.

        ``language_code`` may be a documented BCP-47 code or ``"unknown"``
        for automatic detection. ``api_key`` supports secure dependency
        injection and is never persisted or logged.
        """
        load_project_environment()
        self._api_key = api_key or os.environ.get("SARVAM_API_KEY")
        self._model = model
        self._mode = mode
        self._language_code = language_code
        self._timeout_seconds = timeout_seconds

    @property
    def provider_name(self) -> str:
        """Return the stable provider identifier used in ``ASRResponse``."""
        return SARVAM_PROVIDER_NAME

    def transcribe(self, audio_path: Path) -> ASRResponse:
        """Upload ``audio_path`` to Sarvam and return a standard response.

        Raises:
            AudioFileNotFoundError: If the requested path does not exist.
            TranscriptionError: If configuration, upload, API, or response
                parsing fails.
        """
        if not audio_path.exists():
            raise AudioFileNotFoundError(f"Audio file not found: {audio_path}")
        if not self._api_key:
            raise TranscriptionError(
                "SARVAM_API_KEY must be set before using SarvamASRProvider"
            )

        try:
            body, content_type = self._build_multipart_body(audio_path)
            request = Request(
                SARVAM_STT_URL,
                data=body,
                headers={
                    "api-subscription-key": self._api_key,
                    "Content-Type": content_type,
                },
                method="POST",
            )
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))

            transcript = payload.get("transcript")
            if not isinstance(transcript, str):
                raise TranscriptionError(
                    "Sarvam Speech-to-Text response did not contain a transcript"
                )

            return ASRResponse(
                text=transcript,
                language=self._optional_string(payload.get("language_code")),
                provider=self.provider_name,
                request_id=self._optional_string(payload.get("request_id")),
            )
        except (AudioFileNotFoundError, TranscriptionError):
            raise
        except HTTPError as exc:
            raise TranscriptionError(
                f"Sarvam Speech-to-Text request failed with HTTP {exc.code}"
            ) from exc
        except (URLError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise TranscriptionError("Sarvam Speech-to-Text transcription failed") from exc

    def _build_multipart_body(self, audio_path: Path) -> tuple[bytes, str]:
        """Build Sarvam's required multipart form without an HTTP dependency."""
        boundary = f"----MediKioskSarvam{uuid4().hex}"
        separator = f"--{boundary}\r\n".encode()
        fields = {"model": self._model, "mode": self._mode}
        if self._language_code is not None:
            fields["language_code"] = self._language_code

        body = bytearray()
        for name, value in fields.items():
            body.extend(separator)
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            body.extend(value.encode())
            body.extend(b"\r\n")

        filename = audio_path.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        media_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        body.extend(separator)
        body.extend(
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        )
        body.extend(f"Content-Type: {media_type}\r\n\r\n".encode())
        body.extend(audio_path.read_bytes())
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        return bytes(body), f"multipart/form-data; boundary={boundary}"

    @staticmethod
    def _optional_string(value: object) -> str | None:
        """Keep optional Sarvam string fields within the ASRResponse contract."""
        return value if isinstance(value, str) else None
