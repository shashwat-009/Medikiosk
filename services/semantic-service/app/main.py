from contextlib import asynccontextmanager
import logging
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.detector import SemanticRedFlagDetector, SemanticRedFlagResult

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [semantic-service] %(message)s",
)
logger = logging.getLogger("semantic-service")

# Global detector instance loaded once during startup
detector: Optional[SemanticRedFlagDetector] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load the sentence-transformers model and precompute anchor embeddings
    once on startup. This prevents reload overhead on incoming requests.
    """
    global detector
    logger.info("Initializing SentenceTransformer model and precomputing anchor embeddings...")
    start_time = time.time()
    try:
        detector = SemanticRedFlagDetector()
        duration = time.time() - start_time
        logger.info(
            "Semantic detector initialized successfully in %.2f seconds (cached anchors: %d)",
            duration,
            len(detector._examples),
        )
    except Exception as exc:
        logger.exception("Failed to load SentenceTransformer model on startup: %s", exc)
        detector = None

    yield

    logger.info("Shutting down semantic service...")


app = FastAPI(
    title="MediKiosk Semantic AI Service",
    version="1.0.0",
    description="Multilingual Semantic Red-Flag Detection & Inference Microservice",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="Patient response text to analyze")


class PredictResponse(BaseModel):
    detected: bool
    category: Optional[str] = None
    score: Optional[float] = None
    matched_text: Optional[str] = None
    explanation: Optional[str] = None


@app.get("/")
def root():
    return {
        "service": "semantic-service",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health")
def health():
    is_ready = detector is not None
    return {
        "status": "healthy" if is_ready else "degraded",
        "service": "semantic-service",
        "model_loaded": is_ready,
    }


@app.post("/predict", response_model=PredictResponse)
def predict_red_flag(request: PredictRequest):
    """
    Analyze text input for semantic red flags using multilingual sentence embeddings.
    Returns structured flag detection result with confidence score and matched clinical concept.
    """
    global detector
    if detector is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Semantic model is not loaded or currently unavailable.",
        )

    clean_text = request.text.strip()
    if not clean_text:
        return PredictResponse(
            detected=False,
            category=None,
            score=0.0,
            matched_text=None,
            explanation="Empty text provided.",
        )

    start_time = time.time()
    try:
        result: SemanticRedFlagResult = detector.detect(clean_text)
        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "Prediction completed in %.1f ms | detected: %s | category: %s | score: %s",
            duration_ms,
            result.detected,
            result.category,
            f"{result.score:.3f}" if result.score is not None else "N/A",
        )

        return PredictResponse(
            detected=result.detected,
            category=result.category,
            score=round(result.score, 4) if result.score is not None else None,
            matched_text=result.matched_text,
            explanation=result.explanation,
        )

    except Exception as exc:
        logger.exception("Inference error while analyzing text")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error occurred during semantic inference.",
        ) from None
