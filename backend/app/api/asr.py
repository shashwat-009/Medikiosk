from pathlib import Path
from tempfile import NamedTemporaryFile
import logging
import os

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.api.sessions import get_patient_session

from ai.asr.audio import validate_audio_file
from ai.asr.sarvam_asr import SarvamASRProvider


router = APIRouter(
    prefix="/asr",
    tags=["ASR"],
)

logger = logging.getLogger(__name__)

# Keep this aligned with the existing Sarvam/ASR flow.
# This prevents accidentally accepting arbitrarily large uploads.
MAX_AUDIO_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

ALLOWED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".mp4",
    ".m4a",
    ".webm",
    ".ogg",
    ".flac",
}


# ============================================================
# SHARED AUDIO VALIDATION + SARVAM TRANSCRIPTION
# ============================================================

async def _transcribe_with_sarvam(
    file: UploadFile,
):
    """
    Validate an uploaded audio file, temporarily store it,
    and transcribe it using the existing Sarvam provider.

    No clinical/session data is stored here.
    """

    # --------------------------------------------------------
    # Validate uploaded file
    # --------------------------------------------------------

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Audio file is required",
        )

    suffix = Path(file.filename).suffix.lower()

    if not suffix:
        raise HTTPException(
            status_code=400,
            detail="Audio file must have an extension",
        )

    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported audio format. "
                "Please upload WAV, MP3, MP4, M4A, "
                "WebM, OGG, or FLAC audio."
            ),
        )

    temporary_path: Path | None = None

    try:
        # ----------------------------------------------------
        # Read and store temporary audio
        # ----------------------------------------------------

        content = await file.read()

        if not content:
            raise HTTPException(
                status_code=400,
                detail="Audio file is empty",
            )

        if len(content) > MAX_AUDIO_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Audio file is too large",
            )

        with NamedTemporaryFile(
            delete=False,
            suffix=suffix,
        ) as temporary_file:

            temporary_path = Path(
                temporary_file.name
            )

            temporary_file.write(content)

        # ----------------------------------------------------
        # Validate actual audio file
        # ----------------------------------------------------

        validate_audio_file(
            temporary_path
        )

        # ----------------------------------------------------
        # Sarvam configuration
        # ----------------------------------------------------

        if not settings.sarvam_api_key:
            logger.error(
                "SARVAM_API_KEY is not configured"
            )

            raise HTTPException(
                status_code=500,
                detail="Speech recognition service is not configured",
            )

        # Sarvam provider reads the API key from the environment.
        os.environ["SARVAM_API_KEY"] = (
            settings.sarvam_api_key
        )

        # ----------------------------------------------------
        # Sarvam transcription
        # ----------------------------------------------------

        provider = SarvamASRProvider()

        result = provider.transcribe(
            temporary_path
        )

        return result.model_dump()

    except HTTPException:
        raise

    except FileNotFoundError:
        logger.exception(
            "Temporary audio file disappeared during ASR processing"
        )

        raise HTTPException(
            status_code=400,
            detail="Audio file could not be processed",
        )

    except ValueError:
        logger.exception(
            "Invalid audio supplied for ASR"
        )

        raise HTTPException(
            status_code=400,
            detail="Invalid or unsupported audio file",
        )

    except Exception:
        logger.exception(
            "ASR transcription failed"
        )

        raise HTTPException(
            status_code=502,
            detail="Audio transcription failed",
        )

    finally:
        # ----------------------------------------------------
        # Always remove temporary audio
        # ----------------------------------------------------

        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            try:
                temporary_path.unlink()

            except OSError:
                logger.warning(
                    "Could not remove temporary ASR file: %s",
                    temporary_path,
                )

        await file.close()


# ============================================================
# PRE-SESSION TRANSCRIBE
# ============================================================

@router.post("/pre-session")
async def transcribe_pre_session(
    file: UploadFile = File(...),
):
    """
    Transcribe short identification speech using Sarvam ASR.

    This endpoint is used before a patient session exists,
    for example on the Identify screen.

    It does NOT:
        - create a patient
        - create a session
        - store clinical data
        - store the audio
        - bypass the authenticated clinical ASR endpoint

    It only sends the temporary audio file to Sarvam and
    returns the transcription.
    """

    return await _transcribe_with_sarvam(file)


# ============================================================
# TRANSCRIBE AUDIO
# ============================================================

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    session_id: int | None = None,
    patient_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Transcribe patient speech using Sarvam ASR.

    Authentication:
        X-Patient-Session-Token

    The token must belong to the supplied active session_id.

    The kiosk should automatically send:
        session_id
        X-Patient-Session-Token
        audio file

    ASR itself does not store clinical data.
    The resulting transcription is returned to the caller,
    where it can be used by the conversation flow.
    """

    # --------------------------------------------------------
    # Validate patient session
    # --------------------------------------------------------

    if session_id is None:
        raise HTTPException(
            status_code=400,
            detail="session_id is required",
        )

    if not patient_token:
        raise HTTPException(
            status_code=401,
            detail="Patient session credential is required",
        )

    try:
        get_patient_session(
            session_id=session_id,
            patient_token=patient_token,
            db=db,
        )

    except HTTPException:
        # Preserve the intended authentication/authorization
        # status codes from the session validator.
        raise

    # --------------------------------------------------------
    # Sarvam configuration
    # --------------------------------------------------------

    if not settings.sarvam_api_key:
        logger.error(
            "SARVAM_API_KEY is not configured"
        )

        raise HTTPException(
            status_code=500,
            detail="Speech recognition service is not configured",
        )

    # Sarvam provider reads the API key from the environment.
    os.environ["SARVAM_API_KEY"] = (
        settings.sarvam_api_key
    )

    # --------------------------------------------------------
    # Validate uploaded file
    # --------------------------------------------------------

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Audio file is required",
        )

    suffix = Path(file.filename).suffix.lower()

    if not suffix:
        raise HTTPException(
            status_code=400,
            detail="Audio file must have an extension",
        )

    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported audio format. "
                "Please upload WAV, MP3, MP4, M4A, "
                "WebM, OGG, or FLAC audio."
            ),
        )

    temporary_path: Path | None = None

    try:
        # ----------------------------------------------------
        # Read and store temporary audio
        # ----------------------------------------------------

        content = await file.read()

        if not content:
            raise HTTPException(
                status_code=400,
                detail="Audio file is empty",
            )

        if len(content) > MAX_AUDIO_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Audio file is too large",
            )

        with NamedTemporaryFile(
            delete=False,
            suffix=suffix,
        ) as temporary_file:

            temporary_path = Path(
                temporary_file.name
            )

            temporary_file.write(content)

        # ----------------------------------------------------
        # Validate actual audio file
        # ----------------------------------------------------

        validate_audio_file(
            temporary_path
        )

        # ----------------------------------------------------
        # Sarvam transcription
        # ----------------------------------------------------

        provider = SarvamASRProvider()

        result = provider.transcribe(
            temporary_path
        )

        return result.model_dump()

    except HTTPException:
        raise

    except FileNotFoundError:
        logger.exception(
            "Temporary audio file disappeared during ASR processing"
        )

        raise HTTPException(
            status_code=400,
            detail="Audio file could not be processed",
        )

    except ValueError:
        logger.exception(
            "Invalid audio supplied for ASR"
        )

        raise HTTPException(
            status_code=400,
            detail="Invalid or unsupported audio file",
        )

    except Exception:
        # Never expose raw Sarvam/provider/internal exceptions
        # to the kiosk or patient.
        logger.exception(
            "ASR transcription failed for session %s",
            session_id,
        )

        raise HTTPException(
            status_code=502,
            detail="Audio transcription failed",
        )

    finally:
        # ----------------------------------------------------
        # Always remove temporary audio
        # ----------------------------------------------------

        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            try:
                temporary_path.unlink()

            except OSError:
                logger.warning(
                    "Could not remove temporary ASR file: %s",
                    temporary_path,
                )

        await file.close()