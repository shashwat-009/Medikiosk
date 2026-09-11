from datetime import datetime

from pydantic import BaseModel, Field


class DoctorCreate(BaseModel):
    name: str
    password: str = Field(min_length=8)
    specialization: str | None = None
    department: str | None = None


class DoctorResponse(BaseModel):
    id: int
    name: str
    specialization: str | None
    department: str | None
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True