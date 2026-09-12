import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import decode_token
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
# Configuration
# ============================================================

PATIENT_TOKEN_EXPIRE_MINUTES = 60

# Optional bearer authentication.
#
# This allows session endpoints to accept either:
# - Admin JWT
# - Physician JWT
# - Patient-session token where explicitly permitted
#
# auto_error=False is important because some endpoints allow
# patient-token authentication instead of a JWT.
optional_bearer_scheme = HTTPBearer(auto_error=False)


# ============================================================
# Patient Session Credential Helpers
# ============================================================

def hash_patient_token(token: str) -> str:
    """
    Hash a patient session token.

    The raw patient token is never stored in the database.
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
    Validate a patient-session credential.

    The credential is valid only when:
    - the session exists
    - the session is active
    - the session has a stored token hash
    - the supplied token matches
    - the token has not expired
    """

    if not patient_token or not patient_token.strip():
        raise HTTPException(
            status_code=401,
            detail="Patient session credential required",
        )

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

    provided_token_hash = hash_patient_token(
        patient_token
    )

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
# JWT Helper
# ============================================================

def get_authenticated_actor(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
):
    """
    Validate an Admin or Physician JWT.

    Returns:
        ("admin", None)
        ("physician", Doctor)

    Raises:
        401 for missing/invalid credentials
        403 for unsupported roles
    """

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication credentials required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    subject, role = decode_token(
        credentials.credentials
    )

    if role == "admin":
        return "admin", None

    if role == "physician":
        try:
            doctor_id = int(subject)

        except (ValueError, TypeError):
            raise HTTPException(
                status_code=401,
                detail="Invalid physician credentials",
            )

        doctor = (
            db.query(Doctor)
            .filter(Doctor.id == doctor_id)
            .first()
        )

        if doctor is None:
            raise HTTPException(
                status_code=401,
                detail="Doctor not found",
            )

        if not doctor.is_active:
            raise HTTPException(
                status_code=403,
                detail="Doctor account is inactive",
            )

        return "physician", doctor

    raise HTTPException(
        status_code=403,
        detail="Unsupported authentication role",
    )


# ============================================================
# Session Authorization Helpers
# ============================================================

def require_admin(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
):
    """
    Require an Admin JWT.
    """

    role, actor = get_authenticated_actor(
        credentials,
        db,
    )

    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    return actor


def require_admin_or_physician(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
):
    """
    Require either an Admin JWT or Physician JWT.
    """

    return get_authenticated_actor(
        credentials,
        db,
    )


def require_session_view_access(
    session: SessionModel,
    credentials: HTTPAuthorizationCredentials | None,
    patient_token: str | None,
    db: Session,
):
    """
    Authorize access to a single session.

    Allowed:

    1. Valid patient-session token for this exact session
    2. Admin JWT
    3. Physician JWT belonging to the doctor assigned to
       this exact session

    A physician cannot access another physician's session.
    """

    # --------------------------------------------------------
    # Patient-session authentication
    # --------------------------------------------------------

    if patient_token:
        validated_session = get_patient_session(
            session.id,
            patient_token,
            db,
        )

        return validated_session

    # --------------------------------------------------------
    # Admin / Physician authentication
    # --------------------------------------------------------

    role, actor = get_authenticated_actor(
        credentials,
        db,
    )

    if role == "admin":
        return session

    if role == "physician":
        if session.doctor_id != actor.id:
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this session",
            )

        return session

    raise HTTPException(
        status_code=403,
        detail="You do not have access to this session",
    )


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

    This remains an intentional bootstrap endpoint because
    the patient does not have a patient-session credential yet.

    A short-lived opaque patient credential is generated.
    Only its hash is stored in the database.
    The raw credential is returned once.
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

    # If a doctor was explicitly supplied, verify it exists
    # and is active.
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

        if not doctor.is_active:
            raise HTTPException(
                status_code=400,
                detail="Cannot assign an inactive doctor",
            )

    # Generate high-entropy patient credential.
    patient_token = secrets.token_urlsafe(32)

    # Store only the hash.
    patient_token_hash = hash_patient_token(
        patient_token
    )

    # Short-lived credential.
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

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Could not create patient session",
        )

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
    patient_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Assign an active doctor to a patient session.

    Allowed:
    - Patient with valid token for this exact session
    - Admin

    A physician cannot arbitrarily reassign another session.

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

    # --------------------------------------------------------
    # Authorization
    # --------------------------------------------------------

    if patient_token:

        get_patient_session(
            session_id,
            patient_token,
            db,
        )

    else:

        role, _ = get_authenticated_actor(
            credentials,
            db,
        )

        if role != "admin":
            raise HTTPException(
                status_code=403,
                detail=(
                    "Only the patient session or an admin "
                    "can assign a doctor"
                ),
            )

    # --------------------------------------------------------
    # Mode validation
    # --------------------------------------------------------

    if not mode or not mode.strip():
        raise HTTPException(
            status_code=400,
            detail="Consultation mode is required",
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

    # --------------------------------------------------------
    # Find active doctor
    # --------------------------------------------------------

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

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Could not assign doctor to session",
        )

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
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Return sessions visible to the authenticated user.

    Admin:
        -> all sessions

    Physician:
        -> only sessions assigned to that physician

    Patient:
        -> does not use this endpoint
           because patient access is scoped to one session.
    """

    role, actor = require_admin_or_physician(
        credentials,
        db,
    )

    query = db.query(SessionModel)

    if role == "physician":
        query = query.filter(
            SessionModel.doctor_id == actor.id
        )

    return (
        query
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
    patient_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Get one session.

    Allowed:
    - Patient with valid token for this exact session
    - Assigned physician
    - Admin
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

    require_session_view_access(
        session=session,
        credentials=credentials,
        patient_token=patient_token,
        db=db,
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
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Update session administration data.

    Admin only.

    The patient belonging to an existing session cannot be
    changed. This prevents an existing clinical session from
    being reassigned to another patient.

    The assigned doctor may be changed by an admin.
    """

    require_admin(
        credentials,
        db,
    )

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

    # --------------------------------------------------------
    # Patient cannot be changed after session creation.
    # --------------------------------------------------------

    if session_data.patient_id != session.patient_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "A session cannot be moved to another patient"
            ),
        )

    # --------------------------------------------------------
    # Validate doctor if supplied.
    # --------------------------------------------------------

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

        if not doctor.is_active:
            raise HTTPException(
                status_code=400,
                detail="Cannot assign an inactive doctor",
            )

    session.doctor_id = session_data.doctor_id

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Could not update session",
        )

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
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Delete a session.

    Admin only.

    Active sessions are protected from accidental deletion.
    """

    require_admin(
        credentials,
        db,
    )

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

    if session.status == "active":
        raise HTTPException(
            status_code=400,
            detail=(
                "Active sessions cannot be deleted. "
                "Complete the session before deletion."
            ),
        )

    db.delete(session)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "Session cannot be deleted because "
                "related clinical records exist"
            ),
        )

    return {
        "message": "Session deleted successfully",
    }