# ============================================================
# MediSetu — Semantic Inference Microservice Dockerfile
# Python 3.11 Linux Slim (CPU-only PyTorch & sentence-transformers)
# ============================================================

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    HF_HOME=/root/.cache/huggingface

WORKDIR /app

# Install build dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install lightweight CPU-only PyTorch first to prevent huge CUDA packages
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service application
COPY app /app/app

# Pre-create cache directory for Hugging Face volume mount
RUN mkdir -p /root/.cache/huggingface

# Expose internal service port
EXPOSE 8002

# Healthcheck to verify service and model readiness
HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')" || exit 1

# Start Uvicorn ASGI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
