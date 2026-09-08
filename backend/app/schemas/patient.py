from pydantic import BaseModel, Field


class PatientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    age: int = Field(ge=0, le=150)
    gender: str
    aadhaar: str = Field(min_length=12, max_length=12)


class PatientResponse(BaseModel):
    id: int
    name: str
    age: int
    gender: str
    aadhaar: str | None
    created_at: object

    class Config:
        from_attributes = True