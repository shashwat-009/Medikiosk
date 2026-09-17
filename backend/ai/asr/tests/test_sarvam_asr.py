"""Optional real-API smoke test for :class:`SarvamASRProvider`.

This test is skipped unless a real API key and a non-sensitive audio fixture
are both supplied locally. It is intentionally separate from the offline ASR
unit suite.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ai.asr.sarvam_asr import SARVAM_PROVIDER_NAME, SarvamASRProvider
from ai.asr.schemas import ASRResponse

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_hindi.wav"
SARVAM_API_KEY_PRESENT = bool(os.environ.get("SARVAM_API_KEY"))


@pytest.mark.skipif(
    not SARVAM_API_KEY_PRESENT,
    reason="SARVAM_API_KEY is not set; skipping real Sarvam API smoke test",
)
@pytest.mark.skipif(
    not FIXTURE_PATH.exists(),
    reason=f"No test audio fixture found at {FIXTURE_PATH}",
)
def test_real_sarvam_transcription_returns_valid_asr_response() -> None:
    """A configured real API call returns the standard ASR response type."""
    result = SarvamASRProvider().transcribe(FIXTURE_PATH)

    assert isinstance(result, ASRResponse)
    assert result.provider == SARVAM_PROVIDER_NAME
    assert result.text
