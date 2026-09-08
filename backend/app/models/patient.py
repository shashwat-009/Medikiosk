from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)

    aadhaar = Column(
        String(12),
        nullable=False,
        unique=True,
        index=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())