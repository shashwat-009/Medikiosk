from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.db.database import Base


class Session(Base):
    __tablename__ = "sessions"

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

    doctor_id = Column(
        Integer,
        ForeignKey("doctors.id"),
        nullable=True
    )

    status = Column(
        String,
        nullable=False,
        default="active"
    )

    # Patient-session authentication.
    # Only the hash is stored; the raw token is never persisted.
    session_token_hash = Column(
        String,
        nullable=True,
        unique=True,
        index=True
    )

    session_token_expires_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # ------------------------------------------------------------
    # Persistent session lifecycle
    # ------------------------------------------------------------

    # Updated whenever the patient performs meaningful activity
    # during the consultation.
    last_activity_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # Maximum lifetime of the consultation session.
    expires_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # Set when the consultation is completed.
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # ------------------------------------------------------------
    # Persistent conversation state
    # ------------------------------------------------------------

    # Serialized DialogueState.
    #
    # This makes the database the source of truth instead of the
    # in-memory _managers dictionary in conversations.py.
    conversation_state = Column(
        JSON,
        nullable=True
    )

    # Conversation configuration persisted with the session so that
    # the DialogueManager can be reconstructed after a restart.
    complaint = Column(
        String,
        nullable=True
    )

    language = Column(
        String,
        nullable=True
    )

    mode = Column(
        String,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )