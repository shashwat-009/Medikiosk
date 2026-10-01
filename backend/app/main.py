import sys
from pathlib import Path

# Ensure backend directory is in sys.path (for app and ai packages)
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_BACKEND_DIR_STR = str(_BACKEND_DIR)
if _BACKEND_DIR_STR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR_STR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import Base, engine

from app.models.patient import Patient
from app.models.session import Session
from app.models.document import Document
from app.models.response import Response
from app.models.summary import Summary
from app.models.doctor import Doctor
from app.models.consent import Consent

from app.api.tts import router as tts_router
from app.api.patients import router as patients_router
from app.api.sessions import router as sessions_router
from app.api.documents import router as documents_router
from app.api.responses import router as responses_router
from app.api.summary import router as summary_router
from app.api.doctors import router as doctors_router
from app.api.consent import router as consent_router
from app.api.asr import router as asr_router
from app.api.conversations import router as conversation_router
from app.api.auth import router as auth_router


Base.metadata.create_all(bind=engine)


def _seed_default_doctors():
    """Ensure default active physicians exist for General Medicine and AYUSH departments."""
    from app.db.database import SessionLocal
    from pwdlib import PasswordHash

    db = SessionLocal()
    try:
        has_general = (
            db.query(Doctor)
            .filter(Doctor.department.ilike("General Medicine"), Doctor.is_active.is_(True))
            .first()
        )
        has_ayush = (
            db.query(Doctor)
            .filter(Doctor.department.ilike("AYUSH"), Doctor.is_active.is_(True))
            .first()
        )

        p_hash = PasswordHash.recommended()
        docs_to_add = []

        if not has_general:
            docs_to_add.append(
                Doctor(
                    name="Dr. Rajesh Sharma",
                    specialization="General Medicine",
                    department="General Medicine",
                    password_hash=p_hash.hash("doctor123"),
                    role="physician",
                    is_active=True,
                )
            )

        if not has_ayush:
            docs_to_add.append(
                Doctor(
                    name="Dr. Ananya Verma",
                    specialization="AYUSH (Ayurveda)",
                    department="AYUSH",
                    password_hash=p_hash.hash("doctor123"),
                    role="physician",
                    is_active=True,
                )
            )

        if docs_to_add:
            db.add_all(docs_to_add)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


_seed_default_doctors()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version
)


# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# API Routers
# =========================

app.include_router(patients_router)
app.include_router(sessions_router)
app.include_router(documents_router)
app.include_router(responses_router)
app.include_router(summary_router)
app.include_router(doctors_router)
app.include_router(consent_router)
app.include_router(asr_router)
app.include_router(conversation_router)
app.include_router(tts_router)
app.include_router(auth_router)

@app.get("/")
def root():
    return {
        "message": "MediSetu API is running",
        "status": "success"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }