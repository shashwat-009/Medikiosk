import json
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.auth import (
    decode_token,
    require_admin,
)
from app.db.database import get_db
from app.models.doctor import Doctor
from app.models.session import Session as SessionModel
from app.models.summary import Summary
from app.schemas.summary import (
    SummaryCreate,
    SummaryResponse,
    SummaryUpdate,
)
from app.services.summary_service import (
    generate_deterministic_summary,
)


router = APIRouter(
    prefix="/summaries",
    tags=["Summaries"],
)


# ------------------------------------------------------------
# Optional physician authentication
#
# We use an optional bearer scheme because patient requests
# authenticate through X-Patient-Session-Token instead.
# ------------------------------------------------------------

physician_bearer = HTTPBearer(
    auto_error=False
)


# ============================================================
# PATIENT SESSION AUTHENTICATION
# ============================================================

def hash_patient_token(token: str) -> str:
    """
    Hash the patient-session token using SHA-256.

    The raw token is never stored in the database.
    """
    import hashlib

    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def get_patient_session(
    session_id: int,
    patient_token: str,
    db: Session,
):
    """
    Validate a patient session token and return the session.

    Requirements:
    - session must exist
    - session must be active
    - token hash must exist
    - supplied token must match
    - token must not be expired
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
            status_code=403,
            detail="Session is not active",
        )

    if not session.session_token_hash:
        raise HTTPException(
            status_code=403,
            detail="Patient session authentication is unavailable",
        )

    supplied_hash = hash_patient_token(
        patient_token
    )

    if not secrets.compare_digest(
        supplied_hash,
        session.session_token_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid patient session token",
        )

    if (
        session.session_token_expires_at
        is not None
    ):
        from datetime import datetime, timezone

        if (
            datetime.now(timezone.utc)
            >= session.session_token_expires_at
        ):
            raise HTTPException(
                status_code=401,
                detail="Patient session token has expired",
            )

    return session


# ============================================================
# PHYSICIAN AUTHENTICATION
# ============================================================

def get_authenticated_physician(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
):
    """
    Validate a physician JWT.

    Returns:
        Doctor object

    Returns None when no bearer token is supplied.
    """

    if credentials is None:
        return None

    try:
        payload = decode_token(
            credentials.credentials
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
        ) from exc

    if payload.get("role") != "physician":
        raise HTTPException(
            status_code=403,
            detail="Physician access required",
        )

    doctor_id = payload.get("sub")

    if doctor_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid physician token",
        )

    try:
        doctor_id = int(doctor_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid physician identity",
        ) from exc

    doctor = (
        db.query(Doctor)
        .filter(
            Doctor.id == doctor_id,
            Doctor.is_active.is_(True),
        )
        .first()
    )

    if doctor is None:
        raise HTTPException(
            status_code=401,
            detail="Physician not found or inactive",
        )

    return doctor


# ============================================================
# SUMMARY ACCESS HELPERS
# ============================================================

def require_summary_access(
    summary: Summary,
    patient_token: str | None,
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
):
    """
    Allow access when either:

    1. The request has a valid patient-session token for the
       summary's session.

    OR

    2. The request has a valid physician JWT and that physician
       is assigned to the summary's session.

    Returns:
        ("patient", session)
        ("physician", doctor)
    """

    # --------------------------------------------------------
    # Patient access
    # --------------------------------------------------------

    if patient_token:
        session = get_patient_session(
            session_id=summary.session_id,
            patient_token=patient_token,
            db=db,
        )

        return "patient", session

    # --------------------------------------------------------
    # Physician access
    # --------------------------------------------------------

    doctor = get_authenticated_physician(
        credentials=credentials,
        db=db,
    )

    if doctor is not None:

        session = (
            db.query(SessionModel)
            .filter(
                SessionModel.id
                == summary.session_id
            )
            .first()
        )

        if session is None:
            raise HTTPException(
                status_code=404,
                detail="Session not found",
            )

        if session.doctor_id != doctor.id:
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this session",
            )

        return "physician", doctor

    raise HTTPException(
        status_code=401,
        detail="Authentication required",
    )


def require_session_access(
    session_id: int,
    patient_token: str | None,
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
):
    """
    Validate access directly against a session.

    Used for summary generation and creation.
    """

    # --------------------------------------------------------
    # Patient access
    # --------------------------------------------------------

    if patient_token:
        session = get_patient_session(
            session_id=session_id,
            patient_token=patient_token,
            db=db,
        )

        return "patient", session

    # --------------------------------------------------------
    # Physician access
    # --------------------------------------------------------

    doctor = get_authenticated_physician(
        credentials=credentials,
        db=db,
    )

    if doctor is not None:

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

        if session.doctor_id != doctor.id:
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this session",
            )

        return "physician", doctor

    raise HTTPException(
        status_code=401,
        detail="Authentication required",
    )


# ============================================================
# GENERATE SUMMARY
# ============================================================

@router.post(
    "/session/{session_id}/generate",
    response_model=SummaryResponse,
)
def generate_summary(
    session_id: int,
    db: Session = Depends(get_db),
    patient_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        physician_bearer
    ),
):
    """
    Generate and persist the deterministic clinical summary.

    Access:
    - Patient: valid patient-session token
    - Physician: valid JWT + assigned session

    Generated summaries always return to draft status so that
    the physician explicitly reviews the newly generated result.
    """

    access_type, session = require_session_access(
        session_id=session_id,
        patient_token=patient_token,
        credentials=credentials,
        db=db,
    )

    # --------------------------------------------------------
    # Generate deterministic summary
    # --------------------------------------------------------

    try:

        result = generate_deterministic_summary(
            session_id=session_id,
            db=db,
        )

        case_sheet = result["case_sheet"]

        if hasattr(case_sheet, "model_dump"):

            content = case_sheet.model_dump(
                mode="json"
            )

        elif hasattr(case_sheet, "dict"):

            content = case_sheet.dict()

        else:

            raise TypeError(
                "ClinicalCaseSheet is not a supported "
                "serializable model."
            )

        serialized_content = json.dumps(
            content,
            ensure_ascii=False,
        )

        # ----------------------------------------------------
        # Create or update summary
        # ----------------------------------------------------

        summary = (
            db.query(Summary)
            .filter(
                Summary.session_id
                == session_id
            )
            .first()
        )

        if summary is None:

            summary = Summary(
                session_id=session_id,
                content=serialized_content,
                status="draft",
            )

            db.add(summary)

        else:

            summary.content = serialized_content

            # Any regenerated summary must be reviewed again.
            summary.status = "draft"

        db.commit()
        db.refresh(summary)

        return summary

    except ValueError as exc:

        db.rollback()

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except HTTPException:

        db.rollback()
        raise

    except Exception as exc:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Summary generation failed: {exc}",
        ) from exc


# ============================================================
# CREATE SUMMARY
# ============================================================

@router.post(
    "/",
    response_model=SummaryResponse,
)
def create_summary(
    summary_data: SummaryCreate,
    db: Session = Depends(get_db),
    patient_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        physician_bearer
    ),
):
    """
    Create a summary manually.

    Access:
    - Patient session
    - Assigned physician

    This endpoint is primarily useful for internal/MVP
    workflows. Physician review should normally happen through
    the update endpoint.
    """

    require_session_access(
        session_id=summary_data.session_id,
        patient_token=patient_token,
        credentials=credentials,
        db=db,
    )

    # Prevent accidental duplicate summaries.
    existing_summary = (
        db.query(Summary)
        .filter(
            Summary.session_id
            == summary_data.session_id
        )
        .first()
    )

    if existing_summary is not None:

        raise HTTPException(
            status_code=409,
            detail="A summary already exists for this session",
        )

    new_summary = Summary(
        session_id=summary_data.session_id,
        content=summary_data.content,
        status="draft",
    )

    db.add(new_summary)
    db.commit()
    db.refresh(new_summary)

    return new_summary


# ============================================================
# GET ALL SUMMARIES
# ============================================================

@router.get(
    "/",
    response_model=list[SummaryResponse],
)
def get_summaries(
    db: Session = Depends(get_db),
    current_admin=Depends(require_admin),
):
    """
    Administrative endpoint.

    Only an authenticated admin can retrieve all summaries.
    """

    return (
        db.query(Summary)
        .order_by(Summary.id.desc())
        .all()
    )


# ============================================================
# GET ONE SUMMARY
# ============================================================

@router.get(
    "/{summary_id}",
    response_model=SummaryResponse,
)
def get_summary(
    summary_id: int,
    db: Session = Depends(get_db),
    patient_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        physician_bearer
    ),
):
    """
    Retrieve a single summary.

    Access:
    - Patient: valid token for the summary's session
    - Physician: assigned to the summary's session
    """

    summary = (
        db.query(Summary)
        .filter(
            Summary.id == summary_id
        )
        .first()
    )

    if summary is None:

        raise HTTPException(
            status_code=404,
            detail="Summary not found",
        )

    require_summary_access(
        summary=summary,
        patient_token=patient_token,
        credentials=credentials,
        db=db,
    )

    return summary


# ============================================================
# UPDATE SUMMARY
# ============================================================

@router.put(
    "/{summary_id}",
    response_model=SummaryResponse,
)
def update_summary(
    summary_id: int,
    summary_data: SummaryUpdate,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        physician_bearer
    ),
):
    """
    Physician review/update endpoint.

    Only the physician assigned to the session may modify
    summary content or review status.

    Valid statuses:
    - draft
    - accepted
    - rejected
    """

    summary = (
        db.query(Summary)
        .filter(
            Summary.id == summary_id
        )
        .first()
    )

    if summary is None:

        raise HTTPException(
            status_code=404,
            detail="Summary not found",
        )

    doctor = get_authenticated_physician(
        credentials=credentials,
        db=db,
    )

    if doctor is None:
        raise HTTPException(
            status_code=401,
            detail="Physician authentication required",
        )

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id
            == summary.session_id
        )
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    if session.doctor_id != doctor.id:
        raise HTTPException(
            status_code=403,
            detail="You are not assigned to this session",
        )

    # --------------------------------------------------------
    # Validate status
    # --------------------------------------------------------

    if summary_data.status is not None:

        allowed_statuses = {
            "draft",
            "accepted",
            "rejected",
        }

        if summary_data.status not in allowed_statuses:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid summary status. "
                    "Allowed values: draft, accepted, rejected"
                ),
            )

        summary.status = summary_data.status

    # --------------------------------------------------------
    # Update content
    # --------------------------------------------------------

    if summary_data.content is not None:

        summary.content = summary_data.content

    db.commit()
    db.refresh(summary)

    return summary


# ============================================================
# DELETE SUMMARY
# ============================================================

@router.delete(
    "/{summary_id}",
)
def delete_summary(
    summary_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(require_admin),
):
    """
    Delete a summary.

    Administrative action only.
    """

    summary = (
        db.query(Summary)
        .filter(
            Summary.id == summary_id
        )
        .first()
    )

    if summary is None:

        raise HTTPException(
            status_code=404,
            detail="Summary not found",
        )

    db.delete(summary)
    db.commit()

    return {
        "message": "Summary deleted successfully",
    }