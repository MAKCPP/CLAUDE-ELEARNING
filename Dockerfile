# ── Stage 1: build ────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ──────────────────────────────────────────
FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        poppler-utils \
        libreoffice \
        xvfb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code
COPY server.py .
COPY processors/ processors/
COPY static/ static/

# Working directories
RUN mkdir -p jobs outputs

# LibreOffice needs a writable home
ENV HOME=/tmp/lo_home
RUN mkdir -p /tmp/lo_home

EXPOSE 8000

# Start with xvfb-run so LibreOffice has a virtual display
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
