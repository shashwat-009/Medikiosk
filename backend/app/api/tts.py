from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ai.tts import (
    EdgeTTSProvider,
    SynthesisError,
    TTSRequest,
    UnsupportedLanguageError,
)


router = APIRouter(
    prefix="/tts",
    tags=["TTS"],
)


@router.post("/synthesize")
async def synthesize_text(request: TTSRequest):
    """
    Convert patient-facing text into speech.

    This endpoint only handles TTS.
    It does not modify patients, sessions, responses,
    conversations, or clinical data.
    """

    provider = EdgeTTSProvider()

    try:
        result = await provider.synthesize(request)

        audio_path: Path = result.audio_path

        if not audio_path.exists():
            raise HTTPException(
                status_code=500,
                detail="TTS audio file was not generated",
            )

        return FileResponse(
            path=audio_path,
            media_type="audio/mpeg",
            filename=audio_path.name,
        )

    except UnsupportedLanguageError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except SynthesisError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc