from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.session import Session as SessionModel
from app.models.consent import Consent
from app.schemas.consent import ConsentCreate, ConsentResponse
from app.api.sessions import get_patient_session


router = APIRouter(
    prefix="/consents",
    tags=["Consents"],
)


# ============================================================
# Patient Session Authentication
# ============================================================

def require_patient_session(
    session_id: int,
    patient_token: str | None,
    db: Session,
) -> SessionModel:
    """
    Validate the patient credential for the requested session.
    """

    if not patient_token:
        raise HTTPException(
            status_code=401,
            detail="Patient session credential is required",
        )

    return get_patient_session(
        session_id=session_id,
        patient_token=patient_token,
        db=db,
    )


# ============================================================
# Create Consent
# ============================================================

@router.post(
    "/",
    response_model=ConsentResponse,
)
def create_consent(
    consent_data: ConsentCreate,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Create consent for the authenticated patient's active session.
    """

    session = require_patient_session(
        session_id=consent_data.session_id,
        patient_token=x_patient_session_token,
        db=db,
    )

    existing_consent = (
        db.query(Consent)
        .filter(
            Consent.session_id == session.id
        )
        .first()
    )

    if existing_consent is not None:
        raise HTTPException(
            status_code=400,
            detail="Consent already exists for this session",
        )

    new_consent = Consent(
        session_id=session.id,
        capture_consent=consent_data.capture_consent,
        sharing_consent=consent_data.sharing_consent,
        language=consent_data.language,
    )

    db.add(new_consent)
    db.commit()
    db.refresh(new_consent)

    return new_consent


# ============================================================
# Get Consent for a Session
# ============================================================

@router.get(
    "/session/{session_id}",
    response_model=ConsentResponse,
)
def get_session_consent(
    session_id: int,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Retrieve consent for the authenticated patient's session.
    """

    session = require_patient_session(
        session_id=session_id,
        patient_token=x_patient_session_token,
        db=db,
    )

    consent = (
        db.query(Consent)
        .filter(
            Consent.session_id == session.id
        )
        .first()
    )

    if consent is None:
        raise HTTPException(
            status_code=404,
            detail="Consent not found",
        )

    return consent


# ============================================================
# Revoke Consent
# ============================================================

@router.put(
    "/session/{session_id}/revoke",
    response_model=ConsentResponse,
)
def revoke_consent(
    session_id: int,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Revoke consent for the authenticated patient's session.

    Once capture consent is revoked, patient responses can no
    longer be submitted because responses.py checks this state.
    """

    session = require_patient_session(
        session_id=session_id,
        patient_token=x_patient_session_token,
        db=db,
    )

    consent = (
        db.query(Consent)
        .filter(
            Consent.session_id == session.id
        )
        .first()
    )

    if consent is None:
        raise HTTPException(
            status_code=404,
            detail="Consent not found",
        )

    if consent.revoked:
        raise HTTPException(
            status_code=400,
            detail="Consent already revoked",
        )

    consent.revoked = True
    consent.revoked_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(consent)

    return consent