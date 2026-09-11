from fastapi import APIRouter, Depends, HTTPException
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.db.database import get_db

from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.session import Session as SessionModel
from app.models.response import Response
from app.models.document import Document
from app.models.summary import Summary

from app.schemas.doctor import DoctorCreate, DoctorResponse
from app.schemas.session import SessionResponse
from app.schemas.review import DoctorReviewResponse

from app.api.auth import get_current_doctor, require_admin


router = APIRouter(
    prefix="/doctors",
    tags=["Doctors"]
)

password_hash = PasswordHash.recommended()


# -------------------------------------------------------------------
# ADMIN: CREATE DOCTOR
# -------------------------------------------------------------------

@router.post("/", response_model=DoctorResponse)
def create_doctor(
    doctor_data: DoctorCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """
    Create a new physician account.

    Only an authenticated admin can create doctors.
    """

    new_doctor = Doctor(
        name=doctor_data.name,
        password_hash=password_hash.hash(doctor_data.password),
        role="physician",
        is_active=True,
        specialization=doctor_data.specialization,
        department=doctor_data.department,
    )

    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)

    return new_doctor


# -------------------------------------------------------------------
# ADMIN: GET ALL DOCTORS
# -------------------------------------------------------------------

@router.get("/", response_model=list[DoctorResponse])
def get_doctors(
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """
    List all doctor accounts.

    Only an authenticated admin can access this endpoint.
    """

    return db.query(Doctor).all()


# -------------------------------------------------------------------
# GET DOCTOR PROFILE
# -------------------------------------------------------------------

@router.get("/{doctor_id}", response_model=DoctorResponse)
def get_doctor(
    doctor_id: int,
    db: Session = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """
    Get a doctor profile.

    A physician can only access their own profile.
    Admin access to doctor profiles is handled through the
    admin-protected doctor-management endpoints.
    """

    if current_doctor.id != doctor_id:
        raise HTTPException(
            status_code=403,
            detail="You can only access your own doctor profile"
        )

    doctor = (
        db.query(Doctor)
        .filter(Doctor.id == doctor_id)
        .first()
    )

    if doctor is None:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found"
        )

    return doctor


# -------------------------------------------------------------------
# ADMIN: UPDATE DOCTOR
# -------------------------------------------------------------------

@router.put("/{doctor_id}", response_model=DoctorResponse)
def update_doctor(
    doctor_id: int,
    doctor_data: DoctorCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """
    Update a doctor account.

    Only an authenticated admin can update doctors.
    """

    doctor = (
        db.query(Doctor)
        .filter(Doctor.id == doctor_id)
        .first()
    )

    if doctor is None:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found"
        )

    doctor.name = doctor_data.name
    doctor.specialization = doctor_data.specialization
    doctor.department = doctor_data.department

    # Admin can reset the doctor's password.
    if doctor_data.password:
        doctor.password_hash = password_hash.hash(
            doctor_data.password
        )

    db.commit()
    db.refresh(doctor)

    return doctor


# -------------------------------------------------------------------
# ADMIN: DELETE DOCTOR
# -------------------------------------------------------------------

@router.delete("/{doctor_id}")
def delete_doctor(
    doctor_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    """
    Delete a doctor account.

    Only an authenticated admin can delete doctors.
    """

    doctor = (
        db.query(Doctor)
        .filter(Doctor.id == doctor_id)
        .first()
    )

    if doctor is None:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found"
        )

    db.delete(doctor)
    db.commit()

    return {
        "message": "Doctor deleted successfully"
    }


# -------------------------------------------------------------------
# PHYSICIAN: GET ASSIGNED SESSIONS
# -------------------------------------------------------------------

@router.get(
    "/{doctor_id}/sessions",
    response_model=list[SessionResponse]
)
def get_doctor_sessions(
    doctor_id: int,
    db: Session = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """
    Get clinical sessions assigned to the authenticated physician.
    """

    if current_doctor.id != doctor_id:
        raise HTTPException(
            status_code=403,
            detail="You can only access your own assigned sessions"
        )

    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.doctor_id == current_doctor.id)
        .all()
    )

    return sessions


# -------------------------------------------------------------------
# PHYSICIAN: GET COMPLETE SESSION FOR REVIEW
# -------------------------------------------------------------------

@router.get(
    "/{doctor_id}/sessions/{session_id}/review",
    response_model=DoctorReviewResponse
)
def get_session_for_review(
    doctor_id: int,
    session_id: int,
    db: Session = Depends(get_db),
    current_doctor: Doctor = Depends(get_current_doctor),
):
    """
    Get the complete clinical case for physician review.

    The authenticated physician must be the doctor assigned
    to the requested session.
    """

    if current_doctor.id != doctor_id:
        raise HTTPException(
            status_code=403,
            detail="You can only review your own assigned cases"
        )

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id,
            SessionModel.doctor_id == current_doctor.id
        )
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found or not assigned to this doctor"
        )

    # Get patient
    patient = (
        db.query(Patient)
        .filter(Patient.id == session.patient_id)
        .first()
    )

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

    # Get responses
    responses = (
        db.query(Response)
        .filter(Response.session_id == session_id)
        .all()
    )

    # Get documents
    documents = (
        db.query(Document)
        .filter(Document.session_id == session_id)
        .all()
    )

    # Get summary
    summary = (
        db.query(Summary)
        .filter(Summary.session_id == session_id)
        .first()
    )

    return {
        "session": session,
        "patient": patient,
        "responses": responses,
        "documents": documents,
        "summary": summary
    }