import json
import os
import tempfile
from datetime import datetime

from sqlalchemy.orm import Session

from ai.ocr.pipeline import process_document
from app.models.document import Document
from app.services.storage_service import download_document


def process_document_ocr(
    document: Document,
    db: Session,
) -> Document:
    """
    Run the complete Module B OCR + clinical extraction pipeline
    for a stored Document record.

    The original document is stored permanently in Supabase Storage.
    A temporary local copy is created only while the OCR pipeline
    requires a filesystem path.
    """

    if document is None:
        raise ValueError(
            "Document is required."
        )

    if not document.file_path:
        raise ValueError(
            "Document storage path is missing."
        )

    # ============================================================
    # DOWNLOAD FROM SUPABASE TO TEMPORARY LOCAL FILE
    # ============================================================

    extension = os.path.splitext(
        document.filename or document.file_path
    )[1].lower()

    temporary_file_path = None

    try:

        try:
            file_bytes = download_document(
                document.file_path
            )

        except Exception as exc:
            raise FileNotFoundError(
                "Document could not be downloaded "
                f"from Supabase Storage: {exc}"
            )

        # --------------------------------------------------------
        # Create temporary local file
        # --------------------------------------------------------

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=extension,
        ) as temporary_file:

            temporary_file_path = (
                temporary_file.name
            )

            temporary_file.write(
                file_bytes
            )

        # ========================================================
        # MARK AS PROCESSING
        # ========================================================

        document.processing_status = "processing"
        document.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(document)

        try:

            # ====================================================
            # RUN CANONICAL OCR PIPELINE
            # ====================================================

            result = process_document(
                temporary_file_path
            )

            if not result:
                raise RuntimeError(
                    "OCR pipeline returned no result."
                )

            if result.get("status") not in (
                "success",
                "no_text",
            ):
                raise RuntimeError(
                    result.get(
                        "error",
                        "OCR processing failed."
                    )
                )

            # ====================================================
            # OCR TEXT
            # ====================================================

            ocr_text = result.get(
                "text",
                ""
            )

            if ocr_text is None:
                ocr_text = ""

            document.ocr_text = ocr_text

            # ====================================================
            # EXTRACTED CLINICAL DATA
            # ====================================================

            extracted_payload = {
                "document_type": result.get(
                    "document_type"
                ),
                "classification_confidence": result.get(
                    "classification_confidence"
                ),
                "pages": result.get(
                    "pages",
                    []
                ),
                "clinical_entities": result.get(
                    "clinical_entities",
                    {}
                ),
            }

            document.extracted_data = json.dumps(
                extracted_payload,
                ensure_ascii=False,
                default=str,
            )

            # ====================================================
            # OCR CONFIDENCE
            # ====================================================

            confidence = result.get(
                "confidence"
            )

            if confidence is None:
                confidence = result.get(
                    "ocr_confidence"
                )

            if confidence is not None:

                try:
                    document.confidence = float(
                        confidence
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    document.confidence = None

            else:
                document.confidence = None

            # ====================================================
            # MARK AS COMPLETED
            # ====================================================

            document.processing_status = "completed"
            document.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(document)

            return document

        except Exception:

            # ====================================================
            # ROLLBACK
            # ====================================================

            db.rollback()

            # ====================================================
            # MARK AS FAILED
            # ====================================================

            document.processing_status = "failed"
            document.updated_at = datetime.utcnow()

            db.commit()
            db.refresh(document)

            raise

    finally:

        # ========================================================
        # DELETE TEMPORARY LOCAL FILE
        # ========================================================

        if (
            temporary_file_path
            and os.path.exists(
                temporary_file_path
            )
        ):

            try:
                os.remove(
                    temporary_file_path
                )

            except OSError:
                pass