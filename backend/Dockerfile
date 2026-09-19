# ============================================================
# MediKiosk — Main Backend Microservice Dockerfile
# Python 3.11 Linux Slim
# ============================================================

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip to latest version
RUN pip install --no-cache-dir --upgrade pip

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application and AI orchestration code
COPY app /app/app
COPY ai /app/ai

# Pre-create data directory for persistent SQLite database
RUN mkdir -p /app/data

# Expose backend API port
EXPOSE 8000

# Healthcheck to verify FastAPI status
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + str(os.environ.get('PORT', 8000)) + '/health')" || exit 1

# Start Uvicorn ASGI server (uses $PORT provided by Render or defaults to 8000)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
