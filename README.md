# DocVault OCR Service

**FastAPI-based OCR processing with Tesseract, Redis queue, and webhook notifications**

[![CI Status](https://github.com/private-doc-vault/docvault-ocr-service/actions/workflows/ci.yml/badge.svg)](https://github.com/private-doc-vault/docvault-ocr-service/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
- [Running Tests](#running-tests)
- [Building Docker Image](#building-docker-image)
- [API Endpoints](#api-endpoints)
- [Worker Process](#worker-process)
- [Environment Variables](#environment-variables)
- [Development](#development)
- [Contributing](#contributing)

## Overview

DocVault OCR Service is a FastAPI microservice that processes documents using Tesseract OCR. It provides a REST API for task submission, a Redis-based task queue with priority support, a background worker process for OCR execution, and webhook notifications for task completion/failure/progress updates.

### Key Features

- **Tesseract OCR Integration**: High-quality text extraction from images and PDFs
- **Priority Queue System**: Redis-based queue with high/normal/low priorities
- **Background Worker**: Async task processing with progress tracking
- **Webhook Notifications**: HMAC-signed callbacks to backend on status changes
- **Metadata Extraction**: Document categorization and metadata analysis
- **Error Handling**: Robust error handling with retry logic
- **Health Monitoring**: Health check endpoints for container orchestration

## Tech Stack

- **Framework**: FastAPI 0.109+
- **Language**: Python 3.12
- **OCR Engine**: Tesseract 5.3+
- **Queue**: Redis 7+
- **HTTP Client**: httpx (async)
- **Testing**: pytest with async support
- **Validation**: Pydantic v2
- **Image Processing**: Pillow (PIL)

## Prerequisites

- **Python** 3.12+
- **Redis** 7+ (or Docker)
- **Tesseract OCR** 5.3+ with language packs
- **pip** 24+

### Installing Tesseract

**macOS:**
```bash
brew install tesseract tesseract-lang
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-eng libtesseract-dev
```

**Verify installation:**
```bash
tesseract --version
```

## Local Setup

### Option 1: Using Docker (Recommended)

Use the [infrastructure repository](https://github.com/private-doc-vault/docvault-infrastructure) for Docker-based setup:

```bash
git clone --recursive https://github.com/private-doc-vault/docvault-infrastructure.git
cd docvault-infrastructure
./setup.sh
docker-compose -f docker-compose.dev.yml up -d
```

### Option 2: Local Python Environment

1. **Clone the repository:**

```bash
git clone https://github.com/private-doc-vault/docvault-ocr-service.git
cd docvault-ocr-service
```

2. **Create virtual environment:**

```bash
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**

```bash
pip install -r requirements.txt
```

4. **Configure environment:**

Create `.env` file:
```env
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=redis_pass
WEBHOOK_URL=http://localhost:8000/api/webhooks/ocr-status
WEBHOOK_SECRET=<generate-with-openssl-rand-hex-32>
LOG_LEVEL=INFO
TESSERACT_CMD=/usr/bin/tesseract
```

5. **Ensure Redis is running:**

```bash
# Using Docker
docker run -d -p 6379:6379 redis:7

# Or using local Redis
redis-server
```

6. **Start the API server:**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.

7. **Start the worker process** (in a separate terminal):

```bash
source venv/bin/activate
python -m app.worker
```

## Running Tests

### Full Test Suite

```bash
pytest
```

### Run with Verbose Output

```bash
pytest -v
```

### Run with Coverage

```bash
pytest --cov=app --cov-report=html
```

Coverage report will be in `htmlcov/index.html`.

### Run Specific Test Files

```bash
pytest tests/test_ocr_service.py
pytest tests/test_webhook_client.py
```

### Run Tests in Docker

```bash
docker-compose exec ocr-service pytest -v
docker-compose exec ocr-service pytest --cov=app
```

### Test Categories

- **Unit Tests**: `tests/test_ocr_service.py`, `tests/test_webhook_client.py`
- **Integration Tests**: `tests/integration/` - Redis and webhook integration
- **API Tests**: `tests/test_api.py` - FastAPI endpoint tests

## Building Docker Image

### Local Build

```bash
docker build -t docvault-ocr-service:local .
```

### Run Docker Container

```bash
docker run -d \
  -p 8000:8000 \
  -e REDIS_URL="redis://redis:6379" \
  -e REDIS_PASSWORD="redis_pass" \
  -e WEBHOOK_URL="http://backend:8000/api/webhooks/ocr-status" \
  -e WEBHOOK_SECRET="your-secret" \
  -v $(pwd)/documents:/app/documents:ro \
  -v $(pwd)/temp:/app/temp \
  docvault-ocr-service:local
```

### Running Worker in Docker

The Docker image includes both the API server and worker. To run the worker:

```bash
docker exec ocr-service python -m app.worker
```

Or use a separate container with worker command override:

```bash
docker run -d \
  --name ocr-worker \
  -e REDIS_URL="redis://redis:6379" \
  -e WEBHOOK_URL="http://backend:8000/api/webhooks/ocr-status" \
  docvault-ocr-service:local \
  python -m app.worker
```

## API Endpoints

### Health Check

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/health` | Health check endpoint | No |
| GET | `/` | Root endpoint with service info | No |

### OCR Operations

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/ocr/process` | Submit OCR task | No (internal) |
| GET | `/ocr/tasks/{task_id}` | Get task status | No (internal) |
| GET | `/ocr/tasks/{task_id}/result` | Get OCR result | No (internal) |
| DELETE | `/ocr/tasks/{task_id}` | Cancel task | No (internal) |

### Submit OCR Task

**Request:**
```bash
curl -X POST http://localhost:8000/ocr/process \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "123",
    "file_path": "/app/documents/invoice.pdf",
    "priority": "normal",
    "webhook_url": "http://backend:8000/api/webhooks/ocr-status"
  }'
```

**Response:**
```json
{
  "task_id": "ocr:task:abc123",
  "status": "pending",
  "message": "Task queued successfully"
}
```

### Get Task Status

**Request:**
```bash
curl http://localhost:8000/ocr/tasks/ocr:task:abc123
```

**Response:**
```json
{
  "task_id": "ocr:task:abc123",
  "document_id": "123",
  "status": "processing",
  "progress": 50,
  "created_at": "2025-01-01T12:00:00Z",
  "updated_at": "2025-01-01T12:00:30Z"
}
```

### Get OCR Result

**Request:**
```bash
curl http://localhost:8000/ocr/tasks/ocr:task:abc123/result
```

**Response:**
```json
{
  "task_id": "ocr:task:abc123",
  "document_id": "123",
  "status": "completed",
  "result": {
    "text": "Extracted text content...",
    "confidence": 95.5,
    "pages": 3,
    "metadata": {
      "category": "invoice",
      "language": "eng"
    }
  },
  "processing_time": 15.3
}
```

### API Documentation

Interactive API documentation is available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Worker Process

The worker process is a long-running Python script that consumes tasks from the Redis queue and performs OCR processing.

### Worker Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ FastAPI API  │────▶│ Redis Queue  │◀────│Worker Process│
└──────────────┘     │ (Priority)   │     │  (Polling)   │
                     └──────────────┘     └──────┬───────┘
                                                 │
                                    ┌────────────▼──────────┐
                                    │ OCR Processing        │
                                    │ 1. Load document      │
                                    │ 2. Run Tesseract     │
                                    │ 3. Extract metadata   │
                                    │ 4. Store result       │
                                    │ 5. Send webhook       │
                                    └───────────────────────┘
```

### Starting the Worker

**Local environment:**
```bash
python -m app.worker
```

**With custom log level:**
```bash
LOG_LEVEL=DEBUG python -m app.worker
```

**In Docker:**
```bash
docker-compose exec ocr-service python -m app.worker
```

### Worker Features

1. **Priority Processing**: Processes high-priority tasks first
2. **Progress Updates**: Sends progress webhooks (0%, 25%, 50%, 75%, 100%)
3. **Error Handling**: Retries transient errors, reports permanent failures
4. **Graceful Shutdown**: Handles SIGTERM/SIGINT for clean shutdown
5. **Health Monitoring**: Updates task status in Redis
6. **Webhook Notifications**: HMAC-signed callbacks on completion/failure

### Worker Logs

Worker logs are written to:
- **Console**: Standard output (Docker logs)
- **File**: `/app/logs/worker.log` (inside container)

View logs:
```bash
# Docker logs
docker-compose logs -f ocr-service

# Inside container
docker-compose exec ocr-service tail -f /app/logs/worker.log
```

### Monitoring Worker Health

Check if worker is processing tasks:
```bash
# View running processes
docker-compose exec ocr-service ps aux | grep worker

# Check Redis queue length
docker-compose exec redis redis-cli LLEN ocr:queue:high
docker-compose exec redis redis-cli LLEN ocr:queue:normal
docker-compose exec redis redis-cli LLEN ocr:queue:low
```

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `WEBHOOK_URL` | Backend webhook endpoint | `http://backend:8000/api/webhooks/ocr-status` |
| `WEBHOOK_SECRET` | HMAC signing secret | `<random-32-char-hex>` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_PASSWORD` | Redis password | - |
| `LOG_LEVEL` | Logging level | `INFO` |
| `TESSERACT_CMD` | Tesseract binary path | `tesseract` |
| `WORKER_POLL_INTERVAL` | Queue polling interval (seconds) | `1.0` |
| `TASK_TIMEOUT` | Maximum task processing time (seconds) | `300` |
| `RESULT_TTL` | Result storage TTL (seconds) | `3600` |

### Generating Secrets

```bash
# Generate WEBHOOK_SECRET
openssl rand -hex 32
```

**Important**: `WEBHOOK_SECRET` must match the `OCR_WEBHOOK_SECRET` in the backend service.

## Development

### Project Structure

```
.
├── app/
│   ├── main.py              # FastAPI application
│   ├── worker.py            # Background worker process
│   ├── ocr_service.py       # Tesseract OCR integration
│   ├── redis_queue.py       # Redis queue manager
│   ├── webhook_client.py    # Webhook notification client
│   ├── models.py            # Pydantic models
│   ├── routes.py            # API route definitions
│   └── config.py            # Configuration management
├── tests/
│   ├── test_ocr_service.py  # OCR service tests
│   ├── test_webhook_client.py  # Webhook client tests
│   ├── test_api.py          # API endpoint tests
│   └── integration/         # Integration tests
├── logs/                    # Worker logs (not in git)
├── temp/                    # Temporary processing files (not in git)
├── requirements.txt         # Python dependencies
├── Dockerfile              # Docker image definition
├── pytest.ini              # Pytest configuration
└── README.md               # This file
```

### Common Tasks

#### Check Tesseract Installation

```bash
tesseract --version
tesseract --list-langs
```

#### Test OCR on Sample Document

```bash
python -c "
from app.ocr_service import OCRService
ocr = OCRService()
result = ocr.process_document('path/to/document.pdf')
print(result)
"
```

#### Monitor Redis Queue

```bash
# Connect to Redis CLI
redis-cli -a redis_pass

# View all keys
KEYS ocr:*

# Check queue lengths
LLEN ocr:queue:high
LLEN ocr:queue:normal
LLEN ocr:queue:low

# View task metadata
HGETALL ocr:task:abc123

# Get task result
GET ocr:result:abc123
```

#### Send Test Webhook

```bash
python -c "
import asyncio
from app.webhook_client import WebhookClient
client = WebhookClient('http://localhost:8000/api/webhooks/ocr-status', 'your-secret')
asyncio.run(client.send_completion('123', 'task123', {'text': 'test'}, 10.5))
"
```

### Code Quality

```bash
# Format code with black
black app/ tests/

# Lint with flake8
flake8 app/ tests/

# Type check with mypy
mypy app/

# Sort imports
isort app/ tests/
```

### Debugging

Enable debug logging:
```bash
LOG_LEVEL=DEBUG uvicorn app.main:app --reload
LOG_LEVEL=DEBUG python -m app.worker
```

View detailed logs:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Adding New OCR Features

1. **Update `ocr_service.py`** with new processing logic
2. **Update `models.py`** if response schema changes
3. **Add tests** in `tests/test_ocr_service.py`
4. **Update worker** in `worker.py` if workflow changes
5. **Test end-to-end** with actual documents

## Contributing

Please read the [Contributing Guide](https://github.com/private-doc-vault/docvault-infrastructure/blob/main/CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes and add tests
4. Run tests: `pytest`
5. Run linter: `flake8 app/ tests/`
6. Commit changes: `git commit -m "feat: add my feature"`
7. Push to branch: `git push origin feature/my-feature`
8. Create a Pull Request

### Code Style

- Follow PEP 8 style guide
- Use type hints for function signatures
- Write docstrings for public functions
- Keep functions focused and small (< 50 lines)
- Use meaningful variable names

## License

This project is licensed under the MIT License.

## Related Repositories

- [DocVault Infrastructure](https://github.com/private-doc-vault/docvault-infrastructure) - Docker orchestration
- [DocVault Backend](https://github.com/private-doc-vault/docvault-backend) - Symfony API
- [DocVault Frontend](https://github.com/private-doc-vault/docvault-frontend) - React SPA

## Support

For issues and questions:
- Open an issue in this repository
- Check the [Infrastructure Documentation](https://github.com/private-doc-vault/docvault-infrastructure)
- Review the [CLAUDE.md](https://github.com/private-doc-vault/docvault-infrastructure/blob/main/CLAUDE.md) for AI assistant guidance

## Troubleshooting

### Common Issues

#### Tesseract Not Found

**Error**: `TesseractNotFoundError: tesseract is not installed`

**Solution:**
```bash
# Install Tesseract
brew install tesseract  # macOS
sudo apt-get install tesseract-ocr  # Ubuntu

# Or set TESSERACT_CMD environment variable
export TESSERACT_CMD=/usr/local/bin/tesseract
```

#### Redis Connection Failed

**Error**: `ConnectionError: Error connecting to Redis`

**Solution:**
```bash
# Check Redis is running
redis-cli ping

# Check Redis URL is correct in .env
REDIS_URL=redis://localhost:6379

# Check Redis password if required
REDIS_PASSWORD=redis_pass
```

#### Worker Not Processing Tasks

**Symptom**: Tasks remain in "pending" status

**Solution:**
```bash
# Check worker is running
ps aux | grep worker

# Start worker if not running
python -m app.worker

# Check worker logs for errors
tail -f logs/worker.log
```

#### Webhook Delivery Failed

**Symptom**: Tasks complete but backend not notified

**Solution:**
```bash
# Check webhook URL is accessible
curl -X POST http://backend:8000/api/webhooks/ocr-status

# Verify WEBHOOK_SECRET matches backend OCR_WEBHOOK_SECRET

# Check worker logs for webhook errors
grep "webhook" logs/worker.log
```