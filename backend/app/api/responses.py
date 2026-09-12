from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import require_admin, require_physician
from app.api.sessions import get_patient_session
from app.db.database import get_db
from app.models.response import Response
from app.models.session import Session as SessionModel
from app.models.consent import Consent
from app.models.doctor import Doctor
from app.schemas.response import ResponseCreate, ResponseResponse


router = APIRouter(
    prefix="/responses",
    tags=["Responses"],
)


# ============================================================
# Patient Authentication Helper
# ============================================================

def require_patient_session(
    session_id: int,
    patient_token: str | None,
    db: Session,
) -> SessionModel:
    """
    Authenticate a patient against a specific consultation session.

    The token must:
    - exist
    - match the session
    - be unexpired
    - belong to an active session
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
# Create Response - Patient
# ============================================================

@router.post(
    "/",
    response_model=ResponseResponse,
)
def create_response(
    response: ResponseCreate,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Store a patient's answer.

    Patient authentication:
        X-Patient-Session-Token

    The token is valid only for the specific active session.
    """

    session = require_patient_session(
        session_id=response.session_id,
        patient_token=x_patient_session_token,
        db=db,
    )

    # --------------------------------------------------------
    # Consent validation
    # --------------------------------------------------------

    consent = (
        db.query(Consent)
        .filter(
            Consent.session_id == session.id
        )
        .first()
    )

    if consent is None:
        raise HTTPException(
            status_code=403,
            detail="Consent not found for this session",
        )

    if (
        not consent.capture_consent
        or consent.revoked
    ):
        raise HTTPException(
            status_code=403,
            detail="Valid capture consent is required",
        )

    # --------------------------------------------------------
    # Create response
    # --------------------------------------------------------

    new_response = Response(
        session_id=session.id,
        question=response.question,
        answer=response.answer,
        input_type=response.input_type,
        language=response.language,
    )

    db.add(new_response)
    db.commit()
    db.refresh(new_response)

    return new_response


# ============================================================
# Get All Responses - Admin
# ============================================================

@router.get(
    "/",
    response_model=list[ResponseResponse],
)
def get_responses(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Administrative endpoint.

    Returns all responses.
    """

    return (
        db.query(Response)
        .order_by(Response.id.desc())
        .all()
    )


# ============================================================
# Get One Response - Assigned Physician
# ============================================================

@router.get(
    "/{response_id}",
    response_model=ResponseResponse,
)
def get_response(
    response_id: int,
    current_doctor: Doctor = Depends(
        require_physician
    ),
    db: Session = Depends(get_db),
):
    """
    Allow a physician to view a response only when
    the response belongs to one of their assigned sessions.
    """

    response = (
        db.query(Response)
        .filter(
            Response.id == response_id
        )
        .first()
    )

    if response is None:
        raise HTTPException(
            status_code=404,
            detail="Response not found",
        )

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == response.session_id
        )
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    if session.doctor_id != current_doctor.id:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to access this response",
        )

    return response


# ============================================================
# Update Response - Assigned Physician
# ============================================================

@router.put(
    "/{response_id}",
    response_model=ResponseResponse,
)
def update_response(
    response_id: int,
    response_data: ResponseCreate,
    current_doctor: Doctor = Depends(
        require_physician
    ),
    db: Session = Depends(get_db),
):
    """
    Allow the assigned physician to edit a response.

    The response cannot be moved to another session.
    """

    response = (
        db.query(Response)
        .filter(
            Response.id == response_id
        )
        .first()
    )

    if response is None:
        raise HTTPException(
            status_code=404,
            detail="Response not found",
        )

    # --------------------------------------------------------
    # Prevent changing the response's owning session.
    # --------------------------------------------------------

    if response_data.session_id != response.session_id:
        raise HTTPException(
            status_code=400,
            detail="Response cannot be moved to another session",
        )

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == response.session_id
        )
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    # --------------------------------------------------------
    # Physician ownership check
    # --------------------------------------------------------

    if session.doctor_id != current_doctor.id:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to modify this response",
        )

    response.question = response_data.question
    response.answer = response_data.answer
    response.input_type = response_data.input_type
    response.language = response_data.language

    db.commit()
    db.refresh(response)

    return response


# ============================================================
# Delete Response - Admin
# ============================================================

@router.delete(
    "/{response_id}",
)
def delete_response(
    response_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Administrative deletion of a response.
    """

    response = (
        db.query(Response)
        .filter(
            Response.id == response_id
        )
        .first()
    )

    if response is None:
        raise HTTPException(
            status_code=404,
            detail="Response not found",
        )

    db.delete(response)
    db.commit()

    return {
        "message": "Response deleted successfully",
    }