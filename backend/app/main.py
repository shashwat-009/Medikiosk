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


Base.metadata.create_all(bind=engine)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version
)


# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
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


@app.get("/")
def root():
    return {
        "message": "MediKiosk API is running",
        "status": "success"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }