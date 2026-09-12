import hashlib
import json
import os
import secrets
import tempfile

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ai.ocr.file_validator import validate_file
from app.api.auth import decode_token, require_admin
from app.api.sessions import get_patient_session
from app.db.database import get_db
from app.models.consent import Consent
from app.models.document import Document
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.session import Session as SessionModel
from app.schemas.document import DocumentResponse
from app.services.ocr_service import process_document_ocr
from app.services.storage_service import (
    BUCKET_NAME,
    delete_document as delete_storage_document,
    download_document,
    upload_document as upload_storage_document,
)
from app.services.timeline_service import build_medical_timeline


router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


# ============================================================
# AUTHENTICATION
# ============================================================

optional_bearer_scheme = HTTPBearer(
    auto_error=False
)


def get_authenticated_doctor(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
) -> Doctor | None:
    """
    Authenticate an optional physician JWT.

    Returns:
        Doctor object when a valid physician JWT is supplied.
        None when no bearer credential is supplied.

    Raises:
        HTTPException when a bearer credential is supplied
        but is invalid or does not belong to an active physician.
    """

    if credentials is None:
        return None

    subject, role = decode_token(
        credentials.credentials
    )

    if role != "physician":
        raise HTTPException(
            status_code=403,
            detail="Physician access required",
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
            detail="Doctor not found",
        )

    if not doctor.is_active:
        raise HTTPException(
            status_code=403,
            detail="Doctor account is inactive",
        )

    return doctor


def require_document_access(
    session_id: int,
    patient_token: str | None,
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
) -> SessionModel:
    """
    Authorize access to a document belonging to a session.

    Patient:
        Must provide the patient-session token for the same session.

    Physician:
        Must provide a valid physician JWT and be assigned
        to the requested session.

    Returns:
        The authorized session.
    """

    # --------------------------------------------------------
    # Patient authentication
    # --------------------------------------------------------

    if patient_token:
        return get_patient_session(
            session_id=session_id,
            patient_token=patient_token,
            db=db,
        )

    # --------------------------------------------------------
    # Physician authentication
    # --------------------------------------------------------

    doctor = get_authenticated_doctor(
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
                detail=(
                    "You are not authorized to access "
                    "documents for this session"
                ),
            )

        return session

    raise HTTPException(
        status_code=401,
        detail="Authentication required",
    )


def validate_capture_consent(
    session_id: int,
    db: Session,
) -> Consent:
    """
    Verify that capture consent exists and has not been revoked.
    """

    consent = (
        db.query(Consent)
        .filter(
            Consent.session_id == session_id
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

    return consent


# ============================================================
# STORAGE
# ============================================================

STORAGE_BUCKET = BUCKET_NAME


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
# UPLOAD DOCUMENT - PATIENT
# ============================================================

@router.post(
    "/",
    response_model=DocumentResponse,
)
def upload_document(
    patient_id: int = Form(...),
    session_id: int = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    """
    Upload a patient medical document.

    Patient authentication is required.

    The supplied patient_id must match the patient attached
    to the authenticated consultation session.
    """

    # --------------------------------------------------------
    # Authenticate patient session
    # --------------------------------------------------------

    session = get_patient_session(
        session_id=session_id,
        patient_token=x_patient_session_token or "",
        db=db,
    )

    # --------------------------------------------------------
    # Validate patient/session relationship
    # --------------------------------------------------------

    if session.patient_id != patient_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "Patient is not authorized "
                "for this session"
            ),
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

    # --------------------------------------------------------
    # Validate consent
    # --------------------------------------------------------

    validate_capture_consent(
        session_id=session_id,
        db=db,
    )

    # --------------------------------------------------------
    # Validate document type
    # --------------------------------------------------------

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
            ),
        )

    # --------------------------------------------------------
    # Validate filename
    # --------------------------------------------------------

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required",
        )

    # --------------------------------------------------------
    # Read uploaded file
    # --------------------------------------------------------

    try:
        file_bytes = file.file.read()

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Failed to read uploaded "
                f"document: {exc}"
            ),
        )

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded document is empty",
        )

    # --------------------------------------------------------
    # Validate uploaded file
    # --------------------------------------------------------

    extension = os.path.splitext(
        file.filename
    )[1].lower()

    temporary_validation_path = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=extension,
        ) as temporary_file:

            temporary_validation_path = (
                temporary_file.name
            )

            temporary_file.write(
                file_bytes
            )

        is_valid, error = validate_file(
            temporary_validation_path
        )

        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=error,
            )

    finally:
        if (
            temporary_validation_path
            and os.path.exists(
                temporary_validation_path
            )
        ):
            try:
                os.remove(
                    temporary_validation_path
                )
            except OSError:
                pass

    # --------------------------------------------------------
    # Generate server-side storage path
    # --------------------------------------------------------

    stored_filename = (
        f"{secrets.token_hex(16)}"
        f"{extension}"
    )

    storage_path = (
        f"patients/{patient_id}/"
        f"sessions/{session_id}/"
        f"{stored_filename}"
    )

    # --------------------------------------------------------
    # Upload to Supabase Storage
    # --------------------------------------------------------

    try:
        upload_storage_document(
            file_bytes=file_bytes,
            storage_path=storage_path,
            content_type=(
                file.content_type
                or "application/octet-stream"
            ),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to store document "
                f"in Supabase Storage: {exc}"
            ),
        )

    # --------------------------------------------------------
    # Create document database record
    # --------------------------------------------------------

    new_document = Document(
        patient_id=patient_id,
        session_id=session_id,
        filename=file.filename,
        document_type=document_type,
        file_path=storage_path,
        processing_status="uploaded",
    )

    try:
        db.add(
            new_document
        )

        db.commit()

        db.refresh(
            new_document
        )

    except Exception as exc:

        # Prevent orphaned storage objects.
        try:
            delete_storage_document(
                storage_path
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to create document "
                f"record: {exc}"
            ),
        )

    return new_document


# ============================================================
# PROCESS DOCUMENT
# ============================================================

@router.post(
    "/{document_id}/process",
    response_model=DocumentResponse,
)
def process_document(
    document_id: int,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Process a document using the existing OCR pipeline.

    Access:
        Patient -> own session token
        Physician -> assigned session JWT
    """

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id
        )
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    require_document_access(
        session_id=document.session_id,
        patient_token=x_patient_session_token,
        credentials=credentials,
        db=db,
    )

    if document.processing_status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Document is already being processed",
        )

    try:
        return process_document_ocr(
            document=document,
            db=db,
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Document processing failed: "
                f"{exc}"
            ),
        )


# ============================================================
# GET EXTRACTED CLINICAL DATA
# ============================================================

@router.get(
    "/{document_id}/extracted",
)
def get_extracted_data(
    document_id: int,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Return extracted clinical data.

    Access:
        Patient -> own session token
        Physician -> assigned session JWT
    """

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id
        )
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    require_document_access(
        session_id=document.session_id,
        patient_token=x_patient_session_token,
        credentials=credentials,
        db=db,
    )

    if document.processing_status != "completed":
        raise HTTPException(
            status_code=409,
            detail=(
                "Document has not completed "
                "OCR processing"
            ),
        )

    if not document.extracted_data:
        raise HTTPException(
            status_code=404,
            detail=(
                "No extracted clinical data available"
            ),
        )

    try:
        extracted_data = json.loads(
            document.extracted_data
        )

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail=(
                "Stored extracted data "
                "is invalid JSON"
            ),
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
    "/session/{session_id}/timeline",
)
def get_medical_timeline(
    session_id: int,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Return the medical timeline for a session.

    Access:
        Patient -> own session token
        Physician -> assigned session JWT
    """

    require_document_access(
        session_id=session_id,
        patient_token=x_patient_session_token,
        credentials=credentials,
        db=db,
    )

    return build_medical_timeline(
        session_id=session_id,
        db=db,
    )


# ============================================================
# GET ALL DOCUMENTS - ADMIN
# ============================================================

@router.get(
    "/",
    response_model=list[DocumentResponse],
)
def get_documents(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Administrative document listing.

    Patient and physician users cannot enumerate
    the entire document database.
    """

    return (
        db.query(Document)
        .order_by(Document.id.desc())
        .all()
    )


# ============================================================
# VIEW / DOWNLOAD ORIGINAL DOCUMENT
# ============================================================

@router.get(
    "/{document_id}/file",
)
def view_document_file(
    document_id: int,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Return the original document from Supabase Storage.

    Access:
        Patient -> own session token
        Physician -> assigned session JWT
    """

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id
        )
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    require_document_access(
        session_id=document.session_id,
        patient_token=x_patient_session_token,
        credentials=credentials,
        db=db,
    )

    if not document.file_path:
        raise HTTPException(
            status_code=404,
            detail="Document storage path not found",
        )

    try:
        file_bytes = download_document(
            document.file_path
        )

    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                "Document file not found "
                f"in storage: {exc}"
            ),
        )

    extension = os.path.splitext(
        document.filename or document.file_path
    )[1].lower()

    media_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }

    media_type = media_types.get(
        extension,
        "application/octet-stream",
    )

    safe_filename = os.path.basename(
        document.filename or "document"
    )

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                "inline; "
                f'filename="{safe_filename}"'
            )
        },
    )


# ============================================================
# GET ONE DOCUMENT
# ============================================================

@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
def get_document(
    document_id: int,
    x_patient_session_token: str | None = Header(
        default=None,
        alias="X-Patient-Session-Token",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        optional_bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """
    Return one document only when the caller is authorized
    for the document's session.
    """

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id
        )
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    require_document_access(
        session_id=document.session_id,
        patient_token=x_patient_session_token,
        credentials=credentials,
        db=db,
    )

    return document


# ============================================================
# DELETE DOCUMENT - ADMIN
# ============================================================

@router.delete(
    "/{document_id}",
)
def delete_document(
    document_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Delete a document.

    Restricted to administrators so that a patient or
    physician cannot permanently destroy clinical records.
    """

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id
        )
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    # --------------------------------------------------------
    # Delete from Supabase Storage
    # --------------------------------------------------------

    if document.file_path:

        try:
            delete_storage_document(
                document.file_path
            )

        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Failed to delete document "
                    f"from storage: {exc}"
                ),
            )

    # --------------------------------------------------------
    # Delete database record
    # --------------------------------------------------------

    db.delete(
        document
    )

    db.commit()

    return {
        "message": "Document deleted successfully",
    }