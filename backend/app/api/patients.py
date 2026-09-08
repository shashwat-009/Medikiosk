from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientResponse


router = APIRouter(
    prefix="/patients",
    tags=["Patients"]
)


@router.post("/", response_model=PatientResponse)
def create_patient(
    patient_data: PatientCreate,
    db: Session = Depends(get_db)
):
    # Check whether patient already exists using Aadhaar
    existing_patient = db.query(Patient).filter(
        Patient.aadhaar == patient_data.aadhaar
    ).first()

    if existing_patient is not None:
        # Same Aadhaar = same patient.
        # Do NOT create another patient.
        return existing_patient

    # Create patient only when Aadhaar does not already exist
    new_patient = Patient(
        name=patient_data.name,
        age=patient_data.age,
        gender=patient_data.gender,
        aadhaar=patient_data.aadhaar
    )

    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)

    return new_patient


@router.get("/", response_model=list[PatientResponse])
def get_patients(db: Session = Depends(get_db)):
    return db.query(Patient).all()


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id
    ).first()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

    return patient


@router.put("/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id: int,
    patient_data: PatientCreate,
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id
    ).first()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

    patient.name = patient_data.name
    patient.age = patient_data.age
    patient.gender = patient_data.gender
    patient.aadhaar = patient_data.aadhaar

    db.commit()
    db.refresh(patient)

    return patient


@router.delete("/{patient_id}")
def delete_patient(
    patient_id: int,
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(
        Patient.id == patient_id
    ).first()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

    db.delete(patient)
    db.commit()

    return {
        "message": "Patient deleted successfully"
    }