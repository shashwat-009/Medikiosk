from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.patient import Patient
from app.models.doctor import Doctor
from app.models.session import Session as SessionModel
from app.schemas.session import SessionCreate, SessionResponse


router = APIRouter(
    prefix="/sessions",
    tags=["Sessions"]
)


# ============================================================
# Create Session
# ============================================================

@router.post("/", response_model=SessionResponse)
def create_session(
    session_data: SessionCreate,
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(
        Patient.id == session_data.patient_id
    ).first()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

    if session_data.doctor_id is not None:
        doctor = db.query(Doctor).filter(
            Doctor.id == session_data.doctor_id
        ).first()

        if doctor is None:
            raise HTTPException(
                status_code=404,
                detail="Doctor not found"
            )

    new_session = SessionModel(
        patient_id=session_data.patient_id,
        doctor_id=session_data.doctor_id
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return new_session


# ============================================================
# Assign Doctor to Session
# ============================================================

@router.put(
    "/{session_id}/assign-doctor",
    response_model=SessionResponse
)
def assign_doctor(
    session_id: int,
    mode: str,
    db: Session = Depends(get_db)
):
    """
    Assign a doctor to a patient session based on
    the selected consultation mode.

    MVP routing:
        ayush      -> AYUSH department
        allopathy  -> General Medicine department
    """

    session = db.query(SessionModel).filter(
        SessionModel.id == session_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    normalized_mode = mode.strip().lower()

    if normalized_mode == "ayush":
        department = "AYUSH"

    elif normalized_mode == "allopathy":
        department = "General Medicine"

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid consultation mode."
        )

    # Find an available doctor in the required department.
    doctor = db.query(Doctor).filter(
        Doctor.department.ilike(department)
    ).first()

    if doctor is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No doctor found for {department}. "
                "Please register a doctor for this department."
            )
        )

    session.doctor_id = doctor.id

    db.commit()
    db.refresh(session)

    return session


# ============================================================
# Get All Sessions
# ============================================================

@router.get("/", response_model=list[SessionResponse])
def get_sessions(
    db: Session = Depends(get_db)
):
    return db.query(SessionModel).all()


# ============================================================
# Get One Session
# ============================================================

@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: int,
    db: Session = Depends(get_db)
):
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    return session


# ============================================================
# Update Session
# ============================================================

@router.put("/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: int,
    session_data: SessionCreate,
    db: Session = Depends(get_db)
):
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    patient = db.query(Patient).filter(
        Patient.id == session_data.patient_id
    ).first()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

    if session_data.doctor_id is not None:
        doctor = db.query(Doctor).filter(
            Doctor.id == session_data.doctor_id
        ).first()

        if doctor is None:
            raise HTTPException(
                status_code=404,
                detail="Doctor not found"
            )

    session.patient_id = session_data.patient_id
    session.doctor_id = session_data.doctor_id

    db.commit()
    db.refresh(session)

    return session


# ============================================================
# Delete Session
# ============================================================

@router.delete("/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db)
):
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    db.delete(session)
    db.commit()

    return {
        "message": "Session deleted successfully"
    }