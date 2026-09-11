from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func

from app.db.database import Base


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String,
        nullable=False
    )

    specialization = Column(
        String,
        nullable=True
    )

    department = Column(
        String,
        nullable=True
    )

    # Authentication
    password_hash = Column(
        String,
        nullable=False
    )

    # Authorization
    role = Column(
        String,
        nullable=False,
        default="physician"
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )