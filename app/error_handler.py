"""
Comprehensive error handling for OCR service
Handles validation errors, processing errors, and system errors
"""
import logging
from typing import Dict, Optional, List, Any
from datetime import datetime
from enum import Enum

from .models import TaskStatus, ErrorResponse


logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    """Types of errors that can occur"""
    # Validation errors
    INVALID_FILE_TYPE = "invalid_file_type"
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_LANGUAGE = "unsupported_language"

    # Processing errors
    TESSERACT_ERROR = "tesseract_error"
    CORRUPTED_FILE = "corrupted_file"
    TIMEOUT = "timeout"

    # System errors
    REDIS_ERROR = "redis_error"
    DISK_FULL = "disk_full"
    MISSING_DEPENDENCY = "missing_dependency"
    PROCESSING_LIMIT = "processing_limit"

    # Network errors
    NETWORK_TIMEOUT = "network_timeout"
    CONNECTION_ERROR = "connection_error"


class ErrorDetail(ErrorResponse):
    """Extended error response with additional fields"""
    error: str
    detail: Optional[str] = None
    status_code: int = 500
    retry_after: Optional[int] = None
    task_id: Optional[str] = None
    status: Optional[TaskStatus] = None
    message: Optional[str] = None

    class Config:
        use_enum_values = True


class ErrorHandler:
    """Central error handling and reporting"""

    # Transient errors that should be retried
    RETRYABLE_ERRORS = {
        ErrorType.NETWORK_TIMEOUT,
        ErrorType.CONNECTION_ERROR,
        ErrorType.REDIS_ERROR,
    }

    # Permanent errors that should not be retried
    PERMANENT_ERRORS = {
        ErrorType.INVALID_FILE_TYPE,
        ErrorType.FILE_TOO_LARGE,
        ErrorType.UNSUPPORTED_LANGUAGE,
        ErrorType.CORRUPTED_FILE,
    }

    @staticmethod
    def handle_validation_error(
        error_type: str,
        **kwargs
    ) -> ErrorDetail:
        """
        Handle validation errors

        Args:
            error_type: Type of validation error
            **kwargs: Additional context (filename, size, language, etc.)

        Returns:
            ErrorDetail with appropriate message and status code
        """
        if error_type == "invalid_file_type":
            filename = kwargs.get("filename", "unknown")
            return ErrorDetail(
                error="Invalid file type",
                detail=f"File '{filename}' has an unsupported type. Only PDF, JPG, PNG, and TIFF files are supported.",
                status_code=400
            )

        elif error_type == "file_too_large":
            size = kwargs.get("size", 0)
            max_size = kwargs.get("max_size", 50 * 1024 * 1024)
            size_mb = size / (1024 * 1024)
            max_mb = max_size / (1024 * 1024)
            return ErrorDetail(
                error="File too large",
                detail=f"File size ({size_mb:.1f}MB) exceeds maximum allowed size ({max_mb:.0f}MB).",
                status_code=413
            )

        elif error_type == "unsupported_language":
            language = kwargs.get("language", "unknown")
            return ErrorDetail(
                error="Unsupported language",
                detail=f"Language code '{language}' is not supported. Please check /api/v1/ocr/languages for supported languages.",
                status_code=400
            )

        else:
            return ErrorDetail(
                error="Validation error",
                detail=f"Validation failed: {error_type}",
                status_code=400
            )

    @staticmethod
    def handle_processing_error(
        task_id: str,
        error_type: str,
        error_message: str
    ) -> ErrorDetail:
        """
        Handle OCR processing errors

        Args:
            task_id: Task identifier
            error_type: Type of processing error
            error_message: Error message from processing

        Returns:
            ErrorDetail with task status information
        """
        logger.error(f"Processing error for task {task_id}: {error_type} - {error_message}")

        if error_type == "tesseract_error":
            return ErrorDetail(
                error="OCR processing failed",
                detail=f"Tesseract OCR engine error: {error_message}",
                status_code=500,
                task_id=task_id,
                status=TaskStatus.FAILED,
                message=f"OCR processing failed: {error_message}"
            )

        elif error_type == "corrupted_file":
            return ErrorDetail(
                error="Corrupted file",
                detail=f"Unable to process file: {error_message}",
                status_code=400,
                task_id=task_id,
                status=TaskStatus.FAILED,
                message="File appears to be corrupted or unreadable"
            )

        elif error_type == "timeout":
            return ErrorDetail(
                error="Processing timeout",
                detail=error_message,
                status_code=504,
                task_id=task_id,
                status=TaskStatus.FAILED,
                message="Processing timeout exceeded"
            )

        else:
            return ErrorDetail(
                error="Processing error",
                detail=error_message,
                status_code=500,
                task_id=task_id,
                status=TaskStatus.FAILED,
                message=f"Processing failed: {error_type}"
            )

    @staticmethod
    def handle_timeout_error(
        task_id: str,
        timeout_seconds: int
    ) -> ErrorDetail:
        """
        Handle processing timeout

        Args:
            task_id: Task identifier
            timeout_seconds: Timeout duration in seconds

        Returns:
            ErrorDetail for timeout
        """
        minutes = timeout_seconds / 60
        return ErrorDetail(
            error="Processing timeout",
            detail=f"Task exceeded maximum processing time of {timeout_seconds} seconds ({minutes:.0f} minutes).",
            status_code=504,
            task_id=task_id,
            status=TaskStatus.FAILED,
            message=f"Processing timeout after {timeout_seconds}s"
        )

    @staticmethod
    def handle_redis_error(
        operation: str,
        error_message: str
    ) -> ErrorDetail:
        """
        Handle Redis connection/operation errors

        Args:
            operation: Redis operation that failed
            error_message: Error message

        Returns:
            ErrorDetail for Redis error
        """
        logger.error(f"Redis error during {operation}: {error_message}")

        return ErrorDetail(
            error="Service temporarily unavailable",
            detail=f"Redis connection error during {operation}: {error_message}",
            status_code=503,
            retry_after=30
        )

    @staticmethod
    def handle_system_error(
        error_type: str,
        error_message: str = "",
        dependency: Optional[str] = None
    ) -> ErrorDetail:
        """
        Handle system-level errors

        Args:
            error_type: Type of system error
            error_message: Error message
            dependency: Missing dependency name (if applicable)

        Returns:
            ErrorDetail for system error
        """
        if error_type == "missing_dependency":
            return ErrorDetail(
                error=f"Missing required dependency: {dependency}",
                detail=f"The {dependency} dependency is not installed or not accessible.",
                status_code=503
            )

        elif error_type == "disk_full":
            return ErrorDetail(
                error="Insufficient disk space",
                detail=error_message or "No space left on device",
                status_code=507
            )

        elif error_type == "processing_limit":
            return ErrorDetail(
                error="Processing capacity reached",
                detail=error_message or "Maximum concurrent tasks reached. Please try again later.",
                status_code=503,
                retry_after=60
            )

        else:
            return ErrorDetail(
                error="System error",
                detail=error_message,
                status_code=500
            )

    @staticmethod
    def handle_not_found_error(
        resource_type: str,
        resource_id: str
    ) -> ErrorDetail:
        """
        Handle resource not found errors

        Args:
            resource_type: Type of resource (task, batch, etc.)
            resource_id: Resource identifier

        Returns:
            ErrorDetail for not found error
        """
        return ErrorDetail(
            error=f"{resource_type.capitalize()} not found",
            detail=f"No {resource_type} found with ID: {resource_id}",
            status_code=404
        )

    @staticmethod
    def handle_rate_limit_error(
        client_id: str,
        retry_after: int = 60
    ) -> ErrorDetail:
        """
        Handle rate limit errors

        Args:
            client_id: Client identifier
            retry_after: Seconds until retry is allowed

        Returns:
            ErrorDetail for rate limit error
        """
        logger.warning(f"Rate limit exceeded for client {client_id}")

        return ErrorDetail(
            error="Rate limit exceeded",
            detail=f"Too many requests. Please try again in {retry_after} seconds.",
            status_code=429,
            retry_after=retry_after
        )

    @staticmethod
    def should_retry_error(
        error_type: str,
        retry_count: int,
        max_retries: int = 3
    ) -> bool:
        """
        Determine if an error should be retried

        Args:
            error_type: Type of error
            retry_count: Current retry count
            max_retries: Maximum retry attempts

        Returns:
            True if should retry, False otherwise
        """
        # Check if retry limit exceeded
        if retry_count >= max_retries:
            return False

        # Check if error is retryable
        try:
            error_enum = ErrorType(error_type)
            return error_enum in ErrorHandler.RETRYABLE_ERRORS
        except ValueError:
            # Unknown error type, don't retry
            return False

    @staticmethod
    def calculate_backoff(retry_count: int, base_delay: float = 2.0) -> float:
        """
        Calculate exponential backoff delay

        Args:
            retry_count: Current retry attempt (0-indexed)
            base_delay: Base delay in seconds

        Returns:
            Delay in seconds
        """
        return base_delay * (2 ** retry_count)

    @staticmethod
    def log_error(
        task_id: str,
        error_type: str,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Log error with full context

        Args:
            task_id: Task identifier
            error_type: Type of error
            error_message: Error message
            context: Additional context information
        """
        log_data = {
            "task_id": task_id,
            "error_type": error_type,
            "error_message": error_message,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if context:
            log_data.update(context)

        logger.error(f"Error occurred: {log_data}")

    @staticmethod
    def aggregate_batch_errors(errors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregate errors from batch processing

        Args:
            errors: List of error dictionaries

        Returns:
            Summary of errors
        """
        if not errors:
            return {"total_errors": 0, "unique_errors": [], "most_common_error": None}

        # Count error types
        error_counts: Dict[str, int] = {}
        for error in errors:
            error_msg = error.get("error", "unknown")
            error_counts[error_msg] = error_counts.get(error_msg, 0) + 1

        # Find most common error
        most_common = max(error_counts.items(), key=lambda x: x[1])

        return {
            "total_errors": len(errors),
            "unique_errors": list(error_counts.keys()),
            "most_common_error": most_common[0],
            "error_counts": error_counts
        }
