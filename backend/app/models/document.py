from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    patient_id = Column(
        Integer,
        ForeignKey("patients.id"),
        nullable=False
    )

    session_id = Column(
        Integer,
        ForeignKey("sessions.id"),
        nullable=True
    )

    # Original filename supplied by the user.
    filename = Column(
        String,
        nullable=False
    )

    # prescription / lab_report /
    # discharge_summary / other
    document_type = Column(
        String,
        nullable=False
    )

    # Server-side stored file path.
    file_path = Column(
        String,
        nullable=False
    )

    # ========================================================
    # MODULE B PROCESSING
    # ========================================================

    # B1 starts every new document here.
    #
    # Future states:
    # uploaded
    # processing
    # ocr_complete
    # extracted
    # completed
    # failed
    processing_status = Column(
        String,
        nullable=False,
        default="uploaded"
    )

    # Filled by B2 OCR.
    ocr_text = Column(
        Text,
        nullable=True
    )

    # Filled by later clinical extraction.
    #
    # Stored as JSON text for MVP.
    extracted_data = Column(
        Text,
        nullable=True
    )

    # Overall processing confidence.
    confidence = Column(
        Float,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )