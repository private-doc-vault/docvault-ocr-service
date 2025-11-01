"""
API routes for OCR service
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from typing import Optional, List
import os
from datetime import datetime

from .models import (
    ProcessResponse,
    TaskStatusResponse,
    OCRResult,
    BatchProcessResponse,
    BatchStatusResponse,
    OCRLanguage,
    ErrorResponse,
    TaskStatus
)
from .redis_queue import get_redis_queue_manager
from .validators import validate_file_type, validate_file_size, validate_file_path
from .file_storage import get_file_storage_manager


router = APIRouter(prefix="/api/v1/ocr", tags=["OCR"])


# Supported languages (will be expanded in later tasks)
SUPPORTED_LANGUAGES = [
    {"code": "eng", "name": "English"},
    {"code": "deu", "name": "German"},
    {"code": "fra", "name": "French"},
    {"code": "spa", "name": "Spanish"},
    {"code": "ita", "name": "Italian"},
    {"code": "por", "name": "Portuguese"},
    {"code": "pol", "name": "Polish"},
]


@router.get("/languages", response_model=dict)
async def get_supported_languages():
    """
    Get list of supported OCR languages
    """
    return {"languages": SUPPORTED_LANGUAGES}


@router.post(
    "/process",
    response_model=ProcessResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file or file path"},
        403: {"model": ErrorResponse, "description": "Forbidden file path"},
        413: {"model": ErrorResponse, "description": "File too large"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    }
)
async def process_document(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Form(None),
    language: Optional[str] = Form("eng"),
    document_id: Optional[str] = Form(None)
):
    """
    Process a document for OCR extraction

    Accepts either:
    - **file**: Document file upload (PDF, JPG, PNG, TIFF)
    - **file_path**: Path to document in shared storage

    And:
    - **language**: OCR language code (default: eng)
    - **document_id**: Backend document ID for webhook callbacks (optional)

    Note: Provide either file OR file_path, not both.
    """
    # Validate that exactly one input method is provided
    if file is None and file_path is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "Missing input", "detail": "Either 'file' or 'file_path' must be provided"}
        )

    if file is not None and file_path is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "Ambiguous input", "detail": "Provide either 'file' or 'file_path', not both"}
        )

    redis_manager = get_redis_queue_manager()

    # Handle file_path approach (shared storage)
    if file_path is not None:
        # Validate file path security
        file_path = validate_file_path(file_path)

        # Validate file exists
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "File not found", "detail": f"File does not exist: {file_path}"}
            )

        # Validate file extension
        filename = os.path.basename(file_path)
        if not validate_file_type(filename, None):  # Content type not needed for path-based
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Invalid file type", "detail": "Only PDF, JPG, PNG, and TIFF files are supported"}
            )

        # Validate file size
        file_size = os.path.getsize(file_path)
        if not validate_file_size(file_size):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "File too large", "detail": "Maximum file size is 50MB"}
            )

        # Create task in Redis
        task_id = await redis_manager.create_task(language=language, document_id=document_id)

        # Store file path directly (no need to save, already in shared storage)
        task_key = f"task:{task_id}"
        task_mapping = {
            "file_path": file_path,
            "filename": filename
        }
        if document_id:
            task_mapping["document_id"] = document_id

        await redis_manager.redis.hset(task_key, mapping=task_mapping)

        return ProcessResponse(
            task_id=task_id,
            status=TaskStatus.QUEUED,
            message="Document queued for processing"
        )

    # Handle file upload approach (legacy/backward compatibility)
    else:
        # Validate file type
        if not validate_file_type(file.filename, file.content_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Invalid file type", "detail": "Only PDF, JPG, PNG, and TIFF files are supported"}
            )

        # Read file content to validate size
        content = await file.read()

        if not validate_file_size(len(content)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "File too large", "detail": "Maximum file size is 50MB"}
            )

        # Get file storage manager
        file_storage = get_file_storage_manager()

        # Create task in Redis first to get task_id
        task_id = await redis_manager.create_task(language=language, document_id=document_id)

        # Save file to storage with task_id
        try:
            saved_file_path = file_storage.save_file(
                task_id=task_id,
                filename=file.filename,
                content=content
            )

            # Update task with file path information
            task_key = f"task:{task_id}"
            task_mapping = {
                "file_path": saved_file_path,
                "filename": file.filename
            }
            if document_id:
                task_mapping["document_id"] = document_id

            await redis_manager.redis.hset(task_key, mapping=task_mapping)

        except Exception as e:
            # If file save fails, we should fail the task
            await redis_manager.update_task_status(
                task_id,
                TaskStatus.FAILED,
                message=f"Failed to save file: {str(e)}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "File storage error", "detail": str(e)}
            )

        return ProcessResponse(
            task_id=task_id,
            status=TaskStatus.QUEUED,
            message="Document queued for processing"
        )


@router.get(
    "/status/{task_id}",
    response_model=TaskStatusResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Task not found"}
    }
)
async def get_task_status(task_id: str):
    """
    Get the processing status of a task

    - **task_id**: Unique task identifier
    """
    redis_manager = get_redis_queue_manager()
    task_status = await redis_manager.get_task_status(task_id)

    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Task not found", "detail": f"No task found with ID: {task_id}"}
        )

    return task_status


@router.get(
    "/result/{task_id}",
    response_model=OCRResult,
    responses={
        202: {"description": "Task still processing"},
        404: {"model": ErrorResponse, "description": "Task not found"}
    }
)
async def get_task_result(task_id: str):
    """
    Get the OCR result for a completed task

    - **task_id**: Unique task identifier
    """
    redis_manager = get_redis_queue_manager()

    if not await redis_manager.task_exists(task_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Task not found", "detail": f"No task found with ID: {task_id}"}
        )

    result = await redis_manager.get_result(task_id)

    if not result:
        # Task exists but not completed yet
        task_status = await redis_manager.get_task_status(task_id)
        if task_status.status in [TaskStatus.QUEUED, TaskStatus.PROCESSING]:
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail={"message": "Task still processing", "status": task_status.status}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Result not found", "detail": "Task failed or result not available"}
            )

    return result


@router.post(
    "/batch",
    response_model=BatchProcessResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    }
)
async def process_batch(
    files: List[UploadFile] = File(...),
    language: Optional[str] = Form("eng")
):
    """
    Process multiple documents in batch

    - **files**: List of document files (PDF, JPG, PNG, TIFF)
    - **language**: OCR language code (default: eng)
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "No files provided", "detail": "At least one file must be provided"}
        )

    redis_manager = get_redis_queue_manager()
    file_storage = get_file_storage_manager()
    task_ids = []

    for file in files:
        # Validate each file
        if not validate_file_type(file.filename, file.content_type):
            continue  # Skip invalid files

        content = await file.read()

        if not validate_file_size(len(content)):
            continue  # Skip oversized files

        # Create task for each file
        task_id = await redis_manager.create_task(language=language)

        # Save file to storage
        try:
            file_path = file_storage.save_file(
                task_id=task_id,
                filename=file.filename,
                content=content
            )

            # Update task with file path information
            task_key = f"task:{task_id}"
            await redis_manager.redis.hset(
                task_key,
                mapping={
                    "file_path": file_path,
                    "filename": file.filename
                }
            )

            task_ids.append(task_id)

        except Exception as e:
            # Mark task as failed if file save fails
            await redis_manager.update_task_status(
                task_id,
                TaskStatus.FAILED,
                message=f"Failed to save file: {str(e)}"
            )
            # Continue processing other files

    # Create batch
    batch_id = await redis_manager.create_batch(task_ids)

    return BatchProcessResponse(
        batch_id=batch_id,
        task_ids=task_ids,
        total=len(task_ids),
        message=f"Batch processing started with {len(task_ids)} documents"
    )


@router.get(
    "/batch/{batch_id}",
    response_model=BatchStatusResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Batch not found"}
    }
)
async def get_batch_status(batch_id: str):
    """
    Get the processing status of a batch

    - **batch_id**: Unique batch identifier
    """
    redis_manager = get_redis_queue_manager()
    batch_status = await redis_manager.get_batch_status(batch_id)

    if not batch_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Batch not found", "detail": f"No batch found with ID: {batch_id}"}
        )

    return BatchStatusResponse(**batch_status)
