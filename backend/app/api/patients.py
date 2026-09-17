from datetime import datetime, timezone
import hashlib
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.auth import decode_token
from app.db.database import get_db
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.session import Session as SessionModel
from app.schemas.patient import PatientCreate, PatientResponse


router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
)

# Optional bearer authentication.
#
# Patient endpoints can be accessed either through:
#   1. Patient session token
#   2. Physician JWT
#   3. Admin JWT
#
# Patient creation is the only bootstrap endpoint that does not
# require an existing credential because the patient does not yet
# have a consultation session.
optional_bearer_scheme = HTTPBearer(
    auto_error=False
)


# ============================================================
# PATIENT SESSION TOKEN HELPERS
# ============================================================

def hash_patient_token(token: str) -> str:
    """
    Hash a patient-session token.

    The raw patient token is never stored in the database.
    """

    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def get_patient_from_session_token(
    patient_id: int,
    patient_token: str | None,
    db: Session,
) -> Patient | None:
    """
    Verify that a patient-session token belongs to the
    requested patient and is still active.

    Returns the patient when valid.

    Returns None when no patient token was supplied.

    Raises HTTP 401 when a token was supplied but is invalid,
    expired, or belongs to another patient.
    """

    if not patient_token:
        return None

    token_hash = hash_patient_token(patient_token)

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.session_token_hash == token_hash,
            SessionModel.status == "active",
        )
        .first()
    )

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid patient session credential",
        )

    expires_at = session.session_token_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if (
        expires_at is None
        or expires_at <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=401,
            detail="Patient session credential has expired",
        )


    if session.patient_id != patient_id:
        raise HTTPException(
            status_code=403,
            detail="Patient session does not belong to this patient",
        )

    return (
        db.query(Patient)
        .filter(Patient.id == patient_id)
        .first()
    )


# ============================================================
# JWT ACTOR HELPER
# ============================================================

def get_authenticated_actor(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
):
    """
    Validate an optional MediKiosk JWT.

    Returns:
        ("admin", None)
        ("physician", Doctor)

    Returns None when no JWT was supplied.

    Raises HTTP 401/403 for invalid or unauthorized JWTs.
    """

    if credentials is None:
        return None

    subject, role = decode_token(
        credentials.credentials
    )

    if role == "admin":
        return ("admin", None)

    if role != "physician":
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions",
        )

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
            detail="Physician account not found",
        )

    if not doctor.is_active:
        raise HTTPException(
            status_code=403,
            detail="Physician account is inactive",
        )

    return ("physician", doctor)


# ============================================================
# PHYSICIAN PATIENT ACCESS
# ============================================================

def physician_can_access_patient(
    patient_id: int,
    doctor: Doctor,
    db: Session,
) -> bool:
    """
    A physician may access a patient only when that patient
    has an active consultation session assigned to that physician.
    """

    assigned_session = (
        db.query(SessionModel)
        .filter(
            SessionModel.patient_id == patient_id,
            SessionModel.doctor_id == doctor.id,
            SessionModel.status == "active",
        )
        .first()
    )

    return assigned_session is not None


# ============================================================
# CREATE PATIENT
# ============================================================

@router.post(
    "/",
    response_model=PatientResponse,
)
def create_patient(
    patient_data: PatientCreate,
    db: Session = Depends(get_db),
):
    """
    Create or retrieve a patient during kiosk bootstrap.

    This endpoint intentionally does not require authentication
    because the patient must exist before the first consultation
    session and patient-session credential can be created.

    MVP identity matching:
        Aadhaar -> existing patient

    Actual ABDM/ABHA identity verification is not implemented
    here; this remains the project's demo/mock identity flow.
    """

    aadhaar = patient_data.aadhaar.strip()

    if not aadhaar.isdigit() or len(aadhaar) != 12:
        raise HTTPException(
            status_code=422,
            detail="Aadhaar must contain exactly 12 digits",
        )

    existing_patient = (
        db.query(Patient)
        .filter(
            Patient.aadhaar == aadhaar
        )
        .first()
    )

    if existing_patient is not None:
        return existing_patient

    new_patient = Patient(
        name=patient_data.name.strip(),
        age=patient_data.age,
        gender=patient_data.gender.strip(),
        aadhaar=aadhaar,
    )

    db.add(new_patient)

    try:
        db.commit()

    except Exception:
        db.rollback()

        # A concurrent request may have created the same
        # Aadhaar between our lookup and commit.
        existing_patient = (
            db.query(Patient)
            .filter(
                Patient.aadhaar == aadhaar
            )
            .first()
        )

        if existing_patient is not None:
            return existing_patient

        raise HTTPException(
            status_code=500,
            detail="Unable to create patient",
        )

    db.refresh(new_patient)

    return new_patient


# ============================================================
# GET ALL PATIENTS
# ============================================================

@router.get(
    "/",
    response_model=list[PatientResponse],
)
def get_patients(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Return all patients.

    Administrative endpoint.

    Physicians and patient-session users must not receive
    the complete patient directory.
    """

    actor = get_authenticated_actor(
        credentials,
        db,
    )

    if actor is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    role, _ = actor

    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    return (
        db.query(Patient)
        .order_by(Patient.id.desc())
        .all()
    )


# ============================================================
# GET ONE PATIENT
# ============================================================

@router.get(
    "/{patient_id}",
    response_model=PatientResponse,
)
def get_patient(
    patient_id: int,
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
    Retrieve one patient.

    Allowed:
        - valid patient-session credential for that patient
        - assigned physician
        - admin
    """

    patient = (
        db.query(Patient)
        .filter(
            Patient.id == patient_id
        )
        .first()
    )

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found",
        )

    # Patient-session authentication.
    if patient_token:
        authenticated_patient = get_patient_from_session_token(
            patient_id,
            patient_token,
            db,
        )

        if authenticated_patient is not None:
            return authenticated_patient

    # Physician/admin authentication.
    actor = get_authenticated_actor(
        credentials,
        db,
    )

    if actor is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    role, doctor = actor

    if role == "admin":
        return patient

    if role == "physician" and physician_can_access_patient(
        patient_id,
        doctor,
        db,
    ):
        return patient

    raise HTTPException(
        status_code=403,
        detail="You are not authorized to access this patient",
    )


# ============================================================
# UPDATE PATIENT
# ============================================================

@router.put(
    "/{patient_id}",
    response_model=PatientResponse,
)
def update_patient(
    patient_id: int,
    patient_data: PatientCreate,
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
    Update patient information.

    Allowed:
        - valid patient-session credential for that patient
        - assigned physician
        - admin

    The patient ID cannot be changed.
    """

    patient = (
        db.query(Patient)
        .filter(
            Patient.id == patient_id
        )
        .first()
    )

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found",
        )

    authorized = False

    # Patient-session authentication.
    if patient_token:
        authenticated_patient = get_patient_from_session_token(
            patient_id,
            patient_token,
            db,
        )

        if authenticated_patient is not None:
            authorized = True

    # Physician/admin authentication.
    if not authorized:
        actor = get_authenticated_actor(
            credentials,
            db,
        )

        if actor is not None:
            role, doctor = actor

            if role == "admin":
                authorized = True

            elif role == "physician":
                authorized = physician_can_access_patient(
                    patient_id,
                    doctor,
                    db,
                )

    if not authorized:
        if credentials is None and not patient_token:
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
            )

        raise HTTPException(
            status_code=403,
            detail="You are not authorized to modify this patient",
        )

    aadhaar = patient_data.aadhaar.strip()

    if not aadhaar.isdigit() or len(aadhaar) != 12:
        raise HTTPException(
            status_code=422,
            detail="Aadhaar must contain exactly 12 digits",
        )

    # Prevent changing this patient to an Aadhaar that belongs
    # to another patient.
    existing_patient = (
        db.query(Patient)
        .filter(
            Patient.aadhaar == aadhaar,
            Patient.id != patient_id,
        )
        .first()
    )

    if existing_patient is not None:
        raise HTTPException(
            status_code=409,
            detail="Another patient already uses this Aadhaar",
        )

    patient.name = patient_data.name.strip()
    patient.age = patient_data.age
    patient.gender = patient_data.gender.strip()
    patient.aadhaar = aadhaar

    db.commit()
    db.refresh(patient)

    return patient


# ============================================================
# DELETE PATIENT
# ============================================================

@router.delete(
    "/{patient_id}",
)
def delete_patient(
    patient_id: int,
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Permanently delete a patient.

    Restricted to admin.

    This prevents patients or physicians from deleting
    clinical identity records.
    """

    actor = get_authenticated_actor(
        credentials,
        db,
    )

    if actor is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    role, _ = actor

    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    patient = (
        db.query(Patient)
        .filter(
            Patient.id == patient_id
        )
        .first()
    )

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found",
        )

    db.delete(patient)
    db.commit()

    return {
        "message": "Patient deleted successfully",
    }