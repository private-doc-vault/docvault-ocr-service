"""
Pydantic models for OCR service
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class TaskStatus(str, Enum):
    """Task processing status"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OCRLanguage(BaseModel):
    """Supported OCR language"""
    code: str
    name: str

    class Config:
        json_schema_extra = {
            "example": {
                "code": "eng",
                "name": "English"
            }
        }


class ProcessResponse(BaseModel):
    """Response from OCR process endpoint"""
    task_id: str
    status: TaskStatus
    message: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "abc123-def456",
                "status": "queued",
                "message": "Document queued for processing"
            }
        }


class TaskStatusResponse(BaseModel):
    """Response from status check endpoint"""
    task_id: str
    status: TaskStatus
    progress: Optional[int] = Field(None, ge=0, le=100)
    message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "abc123-def456",
                "status": "processing",
                "progress": 45,
                "message": "Processing document...",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:15Z"
            }
        }


class OCRResult(BaseModel):
    """OCR processing result"""
    text: str
    confidence: float = Field(ge=0.0, le=100.0)
    language: Optional[str] = None
    page_count: Optional[int] = None
    processing_time: Optional[float] = None
    pages: Optional[List] = None
    metadata: Optional[dict] = None
    task_id: Optional[str] = None  # Optional for flexibility

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "abc123-def456",
                "text": "This is the extracted text from the document.",
                "confidence": 95.5,
                "language": "eng",
                "page_count": 1,
                "processing_time": 2.34,
                "metadata": {}
            }
        }


class BatchProcessResponse(BaseModel):
    """Response from batch processing endpoint"""
    batch_id: str
    task_ids: List[str]
    total: int
    message: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "batch_id": "batch-xyz789",
                "task_ids": ["task1", "task2", "task3"],
                "total": 3,
                "message": "Batch processing started"
            }
        }


class BatchStatusResponse(BaseModel):
    """Response from batch status endpoint"""
    batch_id: str
    total: int
    completed: int
    failed: int
    processing: int
    queued: int
    tasks: Optional[List[TaskStatusResponse]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "batch_id": "batch-xyz789",
                "total": 10,
                "completed": 7,
                "failed": 1,
                "processing": 1,
                "queued": 1
            }
        }


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    detail: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "error": "Invalid file type",
                "detail": "Only PDF, JPG, PNG, and TIFF files are supported"
            }
        }
