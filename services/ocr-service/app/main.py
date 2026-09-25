import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ocr.file_validator import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB
from ocr.pipeline import process_document

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ocr-service] %(message)s",
)
logger = logging.getLogger("ocr-service")

app = FastAPI(
    title="MediSetu OCR Service",
    version="1.0.0",
    description="Isolated Module B Document AI & Clinical Extraction Microservice",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_FILE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


@app.get("/")
def root():
    return {
        "service": "ocr-service",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "ocr-service",
    }


@app.post("/process")
async def process_uploaded_document(file: UploadFile = File(...)):
    """
    Process an uploaded medical document through the Module B OCR pipeline.
    Accepts PDF, PNG, JPG, JPEG, WEBP.
    Returns structured OCR text, classified document type, and extracted clinical entities.
    """
    start_time = time.time()

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename.",
        )

    extension = Path(file.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS and extension != ".webp":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{extension}'. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    temp_path = None
    try:
        # Create a secure temporary file with appropriate suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            temp_path = temp_file.name
            size_counter = 0

            # Read file in chunks to avoid unbounded memory consumption
            chunk_size = 1024 * 1024  # 1MB chunks
            while chunk := await file.read(chunk_size):
                size_counter += len(chunk)
                if size_counter > MAX_FILE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_MB} MB.",
                    )
                temp_file.write(chunk)

        logger.info(
            "Starting document OCR processing for file extension: %s (size: %.2f MB)",
            extension,
            size_counter / (1024 * 1024),
        )

        # Run canonical OCR pipeline
        result = process_document(temp_path)

        duration = time.time() - start_time
        logger.info(
            "OCR processing completed in %.2f seconds with status: %s",
            duration,
            result.get("status"),
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OCR engine produced an empty response.",
            )

        if result.get("status") not in ("success", "no_text"):
            error_msg = result.get("error", "Document processing failed.")
            logger.error("OCR pipeline returned failure: %s", error_msg)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unable to extract medical text from this document.",
            )

        return result

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during OCR document processing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred during document processing.",
        ) from None
    finally:
        # Guarantee immediate cleanup of temporary file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
