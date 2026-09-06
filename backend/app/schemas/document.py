from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    id: int
    patient_id: int
    session_id: int | None

    filename: str
    document_type: str
    file_path: str

    processing_status: str

    ocr_text: str | None
    extracted_data: str | None
    confidence: float | None

    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True
    )