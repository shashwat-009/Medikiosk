import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.patient import Patient
from app.models.doctor import Doctor
from app.models.session import Session as SessionModel
from app.schemas.session import (
    SessionCreate,
    SessionCreateResponse,
    SessionResponse,
)


router = APIRouter(
    prefix="/sessions",
    tags=["Sessions"],
)


# ============================================================
# Patient Session Credential Helpers
# ============================================================

PATIENT_TOKEN_EXPIRE_MINUTES = 60


def hash_patient_token(token: str) -> str:
    """
    Hash a patient session token before storing/comparing it.
    The raw token is never persisted in the database.
    """
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def get_patient_session(
    session_id: int,
    patient_token: str,
    db: Session,
) -> SessionModel:
    """
    Validate a patient session credential.

    A patient token is valid only when:
    - the session exists
    - the token matches
    - the token has not expired
    - the session is still active
    """

    session = (
        db.query(SessionModel)
        .filter(SessionModel.id == session_id)
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    if session.status != "active":
        raise HTTPException(
            status_code=401,
            detail="Session is no longer active",
        )

    if not session.session_token_hash:
        raise HTTPException(
            status_code=401,
            detail="Patient session credential is not available",
        )

    provided_token_hash = hash_patient_token(patient_token)

    if not secrets.compare_digest(
        provided_token_hash,
        session.session_token_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid patient session credential",
        )

    if (
        session.session_token_expires_at is None
        or session.session_token_expires_at
        <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=401,
            detail="Patient session credential has expired",
        )

    return session


# ============================================================
# Create Session
# ============================================================

@router.post(
    "/",
    response_model=SessionCreateResponse,
)
def create_session(
    session_data: SessionCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new patient consultation session.

    A short-lived opaque patient credential is generated here.
    Only its hash is stored in the database.

    The raw credential is returned once to the kiosk/patient flow.
    """

    patient = (
        db.query(Patient)
        .filter(
            Patient.id == session_data.patient_id
        )
        .first()
    )

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found",
        )

    if session_data.doctor_id is not None:
        doctor = (
            db.query(Doctor)
            .filter(
                Doctor.id == session_data.doctor_id
            )
            .first()
        )

        if doctor is None:
            raise HTTPException(
                status_code=404,
                detail="Doctor not found",
            )

    # Generate a high-entropy opaque credential.
    patient_token = secrets.token_urlsafe(32)

    # Store only the hash.
    patient_token_hash = hash_patient_token(
        patient_token
    )

    # Credential expires automatically.
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=PATIENT_TOKEN_EXPIRE_MINUTES
        )
    )

    new_session = SessionModel(
        patient_id=session_data.patient_id,
        doctor_id=session_data.doctor_id,
        status="active",
        session_token_hash=patient_token_hash,
        session_token_expires_at=expires_at,
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {
        "id": new_session.id,
        "patient_id": new_session.patient_id,
        "doctor_id": new_session.doctor_id,
        "status": new_session.status,
        "created_at": new_session.created_at,
        "patient_token": patient_token,
        "patient_token_expires_at": expires_at,
    }


# ============================================================
# Assign Doctor to Session
# ============================================================

@router.put(
    "/{session_id}/assign-doctor",
    response_model=SessionResponse,
)
def assign_doctor(
    session_id: int,
    mode: str,
    db: Session = Depends(get_db),
):
    """
    Assign a doctor to a patient session based on
    the selected consultation mode.

    MVP routing:
        ayush      -> AYUSH department
        allopathy  -> General Medicine department
    """

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id
        )
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    if session.status != "active":
        raise HTTPException(
            status_code=400,
            detail="Cannot assign a doctor to an inactive session",
        )

    normalized_mode = mode.strip().lower()

    if normalized_mode == "ayush":
        department = "AYUSH"

    elif normalized_mode == "allopathy":
        department = "General Medicine"

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid consultation mode.",
        )

    doctor = (
        db.query(Doctor)
        .filter(
            Doctor.department.ilike(department),
            Doctor.is_active.is_(True),
        )
        .first()
    )

    if doctor is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No active doctor found for {department}. "
                "Please register a doctor for this department."
            ),
        )

    session.doctor_id = doctor.id

    db.commit()
    db.refresh(session)

    return session


# ============================================================
# Get All Sessions
# ============================================================

@router.get(
    "/",
    response_model=list[SessionResponse],
)
def get_sessions(
    db: Session = Depends(get_db),
):
    """
    Return all sessions.

    NOTE:
    This endpoint will be restricted to admin/physician
    authentication in the next authorization pass.
    """

    return (
        db.query(SessionModel)
        .order_by(SessionModel.id.desc())
        .all()
    )


# ============================================================
# Get One Session
# ============================================================

@router.get(
    "/{session_id}",
    response_model=SessionResponse,
)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
):
    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id
        )
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    return session


# ============================================================
# Update Session
# ============================================================

@router.put(
    "/{session_id}",
    response_model=SessionResponse,
)
def update_session(
    session_id: int,
    session_data: SessionCreate,
    db: Session = Depends(get_db),
):
    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id
        )
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    patient = (
        db.query(Patient)
        .filter(
            Patient.id == session_data.patient_id
        )
        .first()
    )

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found",
        )

    if session_data.doctor_id is not None:
        doctor = (
            db.query(Doctor)
            .filter(
                Doctor.id == session_data.doctor_id
            )
            .first()
        )

        if doctor is None:
            raise HTTPException(
                status_code=404,
                detail="Doctor not found",
            )

    session.patient_id = session_data.patient_id
    session.doctor_id = session_data.doctor_id

    db.commit()
    db.refresh(session)

    return session


# ============================================================
# Delete Session
# ============================================================

@router.delete(
    "/{session_id}",
)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
):
    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id
        )
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    db.delete(session)
    db.commit()

    return {
        "message": "Session deleted successfully",
    }