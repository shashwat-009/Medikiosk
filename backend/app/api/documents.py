import json
import os
import shutil
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from ai.ocr.file_validator import validate_file
from app.db.database import get_db
from app.models.consent import Consent
from app.models.document import Document
from app.models.patient import Patient
from app.models.session import Session as SessionModel
from app.schemas.document import DocumentResponse
from app.services.ocr_service import process_document_ocr
from app.services.timeline_service import build_medical_timeline


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)


# ============================================================
# STORAGE
# ============================================================

UPLOAD_DIR = "uploads"

os.makedirs(
    UPLOAD_DIR,
    exist_ok=True
)


# ============================================================
# DOCUMENT TYPES
# ============================================================

ALLOWED_DOCUMENT_TYPES = {
    "prescription",
    "lab_report",
    "discharge_summary",
    "other",
}


# ============================================================
# UPLOAD DOCUMENT
# ============================================================

@router.post(
    "/",
    response_model=DocumentResponse
)
def upload_document(
    patient_id: int = Form(...),
    session_id: int = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):

    document_type = (
        document_type
        .strip()
        .lower()
    )

    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported document type. "
                "Use prescription, lab_report, "
                "discharge_summary, or other."
            )
        )

    # --------------------------------------------------------
    # Validate patient
    # --------------------------------------------------------

    patient = db.query(
        Patient
    ).filter(
        Patient.id == patient_id
    ).first()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

    # --------------------------------------------------------
    # Validate session
    # --------------------------------------------------------

    session = db.query(
        SessionModel
    ).filter(
        SessionModel.id == session_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    if session.patient_id != patient_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Session does not belong "
                "to this patient"
            )
        )

    # --------------------------------------------------------
    # Validate consent
    # --------------------------------------------------------

    consent = db.query(
        Consent
    ).filter(
        Consent.session_id == session_id
    ).first()

    if consent is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "Consent not found "
                "for this session"
            )
        )

    if (
        not consent.capture_consent
        or consent.revoked
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Valid capture consent "
                "is required"
            )
        )

    # --------------------------------------------------------
    # Validate filename
    # --------------------------------------------------------

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required"
        )

    # --------------------------------------------------------
    # Generate server-side filename
    # --------------------------------------------------------

    extension = os.path.splitext(
        file.filename
    )[1].lower()

    stored_filename = (
        f"{uuid4()}{extension}"
    )

    file_path = os.path.join(
        UPLOAD_DIR,
        stored_filename
    )

    # --------------------------------------------------------
    # Save file
    # --------------------------------------------------------

    try:
        with open(
            file_path,
            "wb"
        ) as buffer:
            shutil.copyfileobj(
                file.file,
                buffer
            )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to store "
                f"document: {exc}"
            )
        )

    # --------------------------------------------------------
    # Validate stored file
    # --------------------------------------------------------

    is_valid, error = validate_file(
        file_path
    )

    if not is_valid:

        try:
            os.remove(file_path)
        except OSError:
            pass

        raise HTTPException(
            status_code=400,
            detail=error
        )

    # --------------------------------------------------------
    # Create document
    # --------------------------------------------------------

    new_document = Document(
        patient_id=patient_id,
        session_id=session_id,
        filename=file.filename,
        document_type=document_type,
        file_path=file_path,
        processing_status="uploaded",
    )

    db.add(
        new_document
    )

    db.commit()

    db.refresh(
        new_document
    )

    return new_document


# ============================================================
# PROCESS DOCUMENT
# ============================================================

@router.post(
    "/{document_id}/process",
    response_model=DocumentResponse
)
def process_document(
    document_id: int,
    db: Session = Depends(get_db)
):

    document = db.query(
        Document
    ).filter(
        Document.id == document_id
    ).first()

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    if document.processing_status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Document is already being processed"
        )

    try:
        return process_document_ocr(
            document=document,
            db=db
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc)
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Document processing failed: "
                f"{exc}"
            )
        )


# ============================================================
# GET EXTRACTED CLINICAL DATA
# ============================================================

@router.get(
    "/{document_id}/extracted"
)
def get_extracted_data(
    document_id: int,
    db: Session = Depends(get_db)
):

    document = db.query(
        Document
    ).filter(
        Document.id == document_id
    ).first()

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    if document.processing_status != "completed":
        raise HTTPException(
            status_code=409,
            detail=(
                "Document has not completed "
                "OCR processing"
            )
        )

    if not document.extracted_data:
        raise HTTPException(
            status_code=404,
            detail="No extracted clinical data available"
        )

    try:
        extracted_data = json.loads(
            document.extracted_data
        )

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Stored extracted data is invalid JSON"
        )

    return {
        "document_id": document.id,
        "patient_id": document.patient_id,
        "session_id": document.session_id,
        "filename": document.filename,
        "document_type": document.document_type,
        "processing_status": document.processing_status,
        "confidence": document.confidence,
        "extracted_data": extracted_data,
    }


# ============================================================
# MEDICAL TIMELINE
# ============================================================

@router.get(
    "/session/{session_id}/timeline"
)
def get_medical_timeline(
    session_id: int,
    db: Session = Depends(get_db)
):
    """
    Return the chronological medical timeline
    for all successfully processed documents
    belonging to a session.
    """

    # --------------------------------------------------------
    # Validate session
    # --------------------------------------------------------

    session = db.query(
        SessionModel
    ).filter(
        SessionModel.id == session_id
    ).first()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    # --------------------------------------------------------
    # Build timeline
    # --------------------------------------------------------

    return build_medical_timeline(
        session_id=session_id,
        db=db
    )


# ============================================================
# GET ALL DOCUMENTS
# ============================================================

@router.get(
    "/",
    response_model=list[DocumentResponse]
)
def get_documents(
    db: Session = Depends(get_db)
):

    return db.query(
        Document
    ).all()


# ============================================================
# GET ONE DOCUMENT
# ============================================================

@router.get(
    "/{document_id}",
    response_model=DocumentResponse
)
def get_document(
    document_id: int,
    db: Session = Depends(get_db)
):

    document = db.query(
        Document
    ).filter(
        Document.id == document_id
    ).first()

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    return document


# ============================================================
# DELETE DOCUMENT
# ============================================================

@router.delete(
    "/{document_id}"
)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db)
):

    document = db.query(
        Document
    ).filter(
        Document.id == document_id
    ).first()

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    # --------------------------------------------------------
    # Delete physical file
    # --------------------------------------------------------

    if os.path.exists(
        document.file_path
    ):
        os.remove(
            document.file_path
        )

    # --------------------------------------------------------
    # Delete database record
    # --------------------------------------------------------

    db.delete(
        document
    )

    db.commit()

    return {
        "message": (
            "Document deleted successfully"
        )
    }