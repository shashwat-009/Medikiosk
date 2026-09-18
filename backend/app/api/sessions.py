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

# Lifetime of the patient-session credential itself.
#
# This is separate from the consultation session lifetime.
PATIENT_TOKEN_EXPIRE_MINUTES = 60

# Maximum amount of inactivity allowed before an active
# consultation becomes expired and can no longer be resumed.
SESSION_INACTIVITY_TIMEOUT_MINUTES = 15

# Maximum total lifetime of one consultation session.
SESSION_MAX_DURATION_MINUTES = 120


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


def _normalize_datetime(
    value: datetime | None,
) -> datetime | None:
    """
    Normalize a database datetime to timezone-aware UTC.

    PostgreSQL/Supabase normally returns timezone-aware values,
    but older rows or SQLite-based tests may contain naive
    datetimes.
    """

    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(timezone.utc)


def _issue_patient_token(
    session: SessionModel,
    now: datetime,
) -> tuple[str, datetime]:
    """
    Generate a fresh patient-session credential.

    Only the hash is stored in the database.
    The raw token is returned to the caller.

    This is used both when creating a new session and when
    resuming an existing session after patient re-login.
    """

    patient_token = secrets.token_urlsafe(32)

    session.session_token_hash = hash_patient_token(
        patient_token
    )

    token_expires_at = (
        now
        + timedelta(
            minutes=PATIENT_TOKEN_EXPIRE_MINUTES
        )
    )

    session.session_token_expires_at = (
        token_expires_at
    )

    return (
        patient_token,
        token_expires_at,
    )


def _session_is_resumable(
    session: SessionModel,
    now: datetime,
) -> bool:
    """
    Determine whether an existing session can be resumed.

    A session is resumable only when:

    - status is active
    - maximum consultation lifetime has not elapsed
    - inactivity timeout has not elapsed

    The patient-session token itself is deliberately NOT checked
    here because a successful re-login issues a fresh token.
    """

    if session.status != "active":
        return False

    # --------------------------------------------------------
    # Maximum consultation lifetime
    # --------------------------------------------------------

    expires_at = _normalize_datetime(
        session.expires_at
    )

    if (
        expires_at is not None
        and expires_at <= now
    ):
        return False

    # --------------------------------------------------------
    # Inactivity timeout
    # --------------------------------------------------------

    last_activity_at = _normalize_datetime(
        session.last_activity_at
    )

    if (
        last_activity_at is not None
        and last_activity_at
        <= now
        - timedelta(
            minutes=SESSION_INACTIVITY_TIMEOUT_MINUTES
        )
    ):
        return False

    return True


def _find_resumable_patient_session(
    patient_id: int,
    db: Session,
) -> SessionModel | None:
    """
    Find the latest active resumable session for a patient.

    The latest activity is preferred.

    Completed sessions are never returned.

    Sessions that are active in the database but have already
    exceeded the inactivity or maximum lifetime are marked
    expired during this lookup.

    This also protects against duplicate active sessions that
    may have been created by older versions of the application.
    """

    now = datetime.now(timezone.utc)

    active_sessions = (
        db.query(SessionModel)
        .filter(
            SessionModel.patient_id == patient_id,
            SessionModel.status == "active",
        )
        .order_by(
            SessionModel.last_activity_at.desc(),
            SessionModel.id.desc(),
        )
        .with_for_update()
        .all()
    )

    resumable_session = None
    changed = False

    for session in active_sessions:

        if _session_is_resumable(
            session,
            now,
        ):
            if resumable_session is None:
                resumable_session = session

            continue

        # The session is marked active in the database but
        # is no longer valid because its lifecycle has ended.
        session.status = "expired"
        changed = True

    if changed:
        try:
            db.commit()

        except IntegrityError:
            db.rollback()

            raise HTTPException(
                status_code=409,
                detail=(
                    "Could not update expired patient sessions"
                ),
            )

    return resumable_session


# ============================================================
# Patient Session Authentication
# ============================================================

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
    - the consultation has not exceeded its maximum lifetime
    - the consultation has not exceeded its inactivity timeout
    """

    if not patient_token or not patient_token.strip():
        raise HTTPException(
            status_code=401,
            detail="Patient session credential required",
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
    # Session lifecycle
    # --------------------------------------------------------

    if session.status != "active":
        raise HTTPException(
            status_code=401,
            detail="Session is no longer active",
        )

    now = datetime.now(timezone.utc)

    # --------------------------------------------------------
    # Maximum consultation lifetime
    # --------------------------------------------------------

    expires_at = _normalize_datetime(
        session.expires_at
    )

    if (
        expires_at is not None
        and expires_at <= now
    ):
        session.status = "expired"
        session.session_token_hash = None
        session.session_token_expires_at = None

        try:
            db.commit()

        except IntegrityError:
            db.rollback()

        raise HTTPException(
            status_code=401,
            detail="Session has expired",
        )

    # --------------------------------------------------------
    # Inactivity timeout
    # --------------------------------------------------------

    last_activity_at = _normalize_datetime(
        session.last_activity_at
    )

    if (
        last_activity_at is not None
        and last_activity_at
        <= now
        - timedelta(
            minutes=SESSION_INACTIVITY_TIMEOUT_MINUTES
        )
    ):
        session.status = "expired"
        session.session_token_hash = None
        session.session_token_expires_at = None

        try:
            db.commit()

        except IntegrityError:
            db.rollback()

        raise HTTPException(
            status_code=401,
            detail="Session expired due to inactivity",
        )

    # --------------------------------------------------------
    # Token existence
    # --------------------------------------------------------

    if not session.session_token_hash:
        raise HTTPException(
            status_code=401,
            detail=(
                "Patient session credential is not available"
            ),
        )

    # --------------------------------------------------------
    # Validate supplied token
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Validate token lifetime
    # --------------------------------------------------------

    token_expires_at = _normalize_datetime(
        session.session_token_expires_at
    )

    if (
        token_expires_at is None
        or token_expires_at <= now
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Patient session credential has expired"
            ),
        )

    # --------------------------------------------------------
    # Successful authenticated request counts as activity.
    # --------------------------------------------------------

    session.last_activity_at = now

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Could not update session activity",
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
            headers={
                "WWW-Authenticate": "Bearer"
            },
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
            .filter(
                Doctor.id == doctor_id
            )
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
                detail=(
                    "You are not assigned to this session"
                ),
            )

        return session

    raise HTTPException(
        status_code=403,
        detail="You do not have access to this session",
    )


# ============================================================
# Create OR Resume Session
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
    Create or resume a patient consultation session.

    This is intentionally an unauthenticated bootstrap endpoint
    because the patient does not have a patient-session credential
    before login.

    Behavior:

    ------------------------------------------------------------
    Existing resumable session
    ------------------------------------------------------------

    If the patient has an active session and has been inactive
    for LESS than 15 minutes:

        -> resume the SAME session

        -> same session ID
        -> same conversation_state
        -> same previous responses
        -> same doctor assignment
        -> fresh patient token
        -> refreshed last_activity_at

    ------------------------------------------------------------
    Expired/inactive session
    ------------------------------------------------------------

    If the patient's existing active session has been inactive
    for 15 minutes or longer:

        -> mark it expired
        -> create a new session

    ------------------------------------------------------------
    Completed session
    ------------------------------------------------------------

    Completed sessions are NEVER resumed.

    A new consultation creates a new session.

    ------------------------------------------------------------
    Maximum lifetime
    ------------------------------------------------------------

    A session cannot be resumed after its 120-minute maximum
    consultation lifetime.

    ------------------------------------------------------------
    Token behavior
    ------------------------------------------------------------

    Every successful login receives a fresh patient-session
    credential.

    The raw credential is returned only in this response.
    Only the SHA-256 hash is stored in the database.
    """

    # --------------------------------------------------------
    # Validate patient.
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Validate explicitly supplied doctor.
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

    # --------------------------------------------------------
    # Try to resume an existing patient session.
    # --------------------------------------------------------

    existing_session = (
        _find_resumable_patient_session(
            patient_id=patient.id,
            db=db,
        )
    )

    now = datetime.now(timezone.utc)

    if existing_session is not None:

        # ----------------------------------------------------
        # RESUME EXISTING SESSION
        # ----------------------------------------------------

        patient_token, token_expires_at = (
            _issue_patient_token(
                existing_session,
                now,
            )
        )

        # The successful login itself is activity.
        existing_session.last_activity_at = now

        # IMPORTANT:
        #
        # Do NOT overwrite:
        #   - conversation_state
        #   - doctor_id
        #   - responses
        #   - session ID
        #   - complaint
        #   - language
        #   - mode
        #
        # The consultation must continue exactly where it stopped.

        try:
            db.commit()

        except IntegrityError:
            db.rollback()

            raise HTTPException(
                status_code=409,
                detail="Could not resume patient session",
            )

        db.refresh(existing_session)

        return {
            "id": existing_session.id,
            "patient_id": existing_session.patient_id,
            "doctor_id": existing_session.doctor_id,
            "status": existing_session.status,
            "created_at": existing_session.created_at,
            "patient_token": patient_token,
            "patient_token_expires_at": token_expires_at,
        }

    # --------------------------------------------------------
    # CREATE NEW SESSION
    # --------------------------------------------------------

    patient_token = secrets.token_urlsafe(32)

    patient_token_hash = hash_patient_token(
        patient_token
    )

    token_expires_at = (
        now
        + timedelta(
            minutes=PATIENT_TOKEN_EXPIRE_MINUTES
        )
    )

    session_expires_at = (
        now
        + timedelta(
            minutes=SESSION_MAX_DURATION_MINUTES
        )
    )

    new_session = SessionModel(
        patient_id=patient.id,
        doctor_id=session_data.doctor_id,
        status="active",
        session_token_hash=patient_token_hash,
        session_token_expires_at=token_expires_at,
        last_activity_at=now,
        expires_at=session_expires_at,
        complaint=getattr(session_data, "complaint", None),
        language=getattr(session_data, "language", None),
        mode=getattr(session_data, "mode", None),
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
        "patient_token_expires_at": token_expires_at,
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
            detail=(
                "Cannot assign a doctor to an inactive session"
            ),
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
# Complete Session
# ============================================================

@router.post(
    "/{session_id}/complete",
)
def complete_session(
    session_id: int,
    patient_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Complete the authenticated patient's consultation session.

    The patient must provide the valid session credential for
    this exact session.

    Completion is idempotent: an already completed session is
    returned without changing its completion timestamp.
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

    if session.status == "completed":
        return {
            "message": "Session already completed",
            "session_id": session.id,
            "status": session.status,
            "completed_at": session.completed_at,
        }

    if session.status != "active":
        raise HTTPException(
            status_code=400,
            detail="Only active sessions can be completed",
        )

    # Validate the patient's credential and lifecycle state.
    get_patient_session(
        session_id,
        patient_token,
        db,
    )

    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)

    # Completed consultations must not retain a usable patient credential.
    session.session_token_hash = None
    session.session_token_expires_at = None

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Could not complete session",
        )

    db.refresh(session)

    return {
        "message": "Session completed successfully",
        "session_id": session.id,
        "status": session.status,
        "completed_at": session.completed_at,
    }


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
# Get Assigned Doctor for Patient Session
# ============================================================

@router.get(
    "/{session_id}/doctor",
)
def get_session_doctor(
    session_id: int,
    patient_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Return the assigned doctor's display information for the
    authenticated patient session.

    Patient access is limited to the active session represented
    by the supplied patient-session credential.
    """

    session = get_patient_session(
        session_id,
        patient_token,
        db,
    )

    if session.doctor_id is None:
        raise HTTPException(
            status_code=404,
            detail="No doctor assigned to this session",
        )

    doctor = (
        db.query(Doctor)
        .filter(
            Doctor.id == session.doctor_id,
            Doctor.is_active.is_(True),
        )
        .first()
    )

    if doctor is None:
        raise HTTPException(
            status_code=404,
            detail="Assigned doctor not found",
        )

    return {
        "id": doctor.id,
        "name": doctor.name,
        "specialization": doctor.specialization,
        "department": doctor.department,
    }


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