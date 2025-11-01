# Python OCR Service Dockerfile for DocVault
# FastAPI + Tesseract OCR + Image Processing
# Optimized for QNAP TS-431P2

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-deu \
        tesseract-ocr-fra \
        tesseract-ocr-spa \
        tesseract-ocr-ita \
        tesseract-ocr-pol \
        libtesseract-dev \
        poppler-utils \
        libmagic1 \
        libpq5 \
        curl \
        git \
        gcc \
        g++ \
        libffi-dev \
        libssl-dev \
        libjpeg-dev \
        zlib1g-dev \
        libtiff-dev \
        libfreetype6-dev \
        liblcms2-dev \
        libwebp-dev \
        libharfbuzz-dev \
        libfribidi-dev \
        libxcb1-dev \
        supervisor \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create application user
RUN groupadd -r ocr && useradd --no-log-init -r -g ocr ocr

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p /app/temp /app/logs /app/documents \
    && chown -R ocr:ocr /app

# Set proper permissions
RUN chmod +x /app/start.sh 2>/dev/null || true

# Create supervisor directories with proper permissions
RUN mkdir -p /app/logs /tmp \
    && chown -R ocr:ocr /app/logs /tmp

# Health check (check both API and worker are running)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Switch to non-root user
USER ocr

# Expose port
EXPOSE 8000

# Start supervisord to manage both FastAPI and worker processes
CMD ["supervisord", "-c", "/app/supervisord.conf"]