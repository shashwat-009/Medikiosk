from datetime import datetime

from pydantic import BaseModel


class SessionCreate(BaseModel):
    patient_id: int
    doctor_id: int | None = None


class SessionResponse(BaseModel):
    id: int
    patient_id: int
    doctor_id: int | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class SessionCreateResponse(SessionResponse):
    patient_token: str
    patient_token_expires_at: datetime