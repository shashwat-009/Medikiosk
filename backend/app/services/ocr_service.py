import json
import os
from datetime import datetime

from sqlalchemy.orm import Session

from ai.ocr.pipeline import process_document
from app.models.document import Document


def process_document_ocr(
    document: Document,
    db: Session,
) -> Document:
    """
    Run the complete Module B OCR + clinical extraction pipeline
    for a stored Document record.
    """

    if document is None:
        raise ValueError("Document is required.")

    if not document.file_path:
        raise ValueError("Document file path is missing.")

    if not os.path.exists(document.file_path):
        raise FileNotFoundError(
            f"Document file not found: {document.file_path}"
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
            document.file_path
        )

        if not result:
            raise RuntimeError(
                "OCR pipeline returned no result."
            )

        if result.get("status") != "success":
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
        #
        # The pipeline stores this as:
        # "confidence"
        #
        # NOT "ocr_confidence".
        # ====================================================

        confidence = result.get(
            "confidence"
        )

        if confidence is None:
            # Backward-compatible fallback in case the
            # pipeline ever returns "ocr_confidence".
            confidence = result.get(
                "ocr_confidence"
            )

        if confidence is not None:
            try:
                document.confidence = float(
                    confidence
                )
            except (TypeError, ValueError):
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