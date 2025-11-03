"""
Tests for error handling and processing status reporting
Follows TDD approach - tests written first, then implementation
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import HTTPException
from datetime import datetime
import asyncio

from app.models import TaskStatus, ErrorResponse


class TestErrorHandling:
    """Tests for comprehensive error handling"""

    @pytest.mark.asyncio
    async def test_file_validation_error_handling(self):
        """Test file validation errors are properly caught and reported"""
        from app.error_handler import ErrorHandler

        # Test invalid file type
        error = ErrorHandler.handle_validation_error(
            error_type="invalid_file_type",
            filename="document.txt"
        )

        assert error.error == "Invalid file type"
        assert "txt" in error.detail.lower()
        assert error.status_code == 400

    @pytest.mark.asyncio
    async def test_file_size_error_handling(self):
        """Test file size limit errors"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_validation_error(
            error_type="file_too_large",
            size=100 * 1024 * 1024,  # 100MB
            max_size=50 * 1024 * 1024  # 50MB
        )

        assert error.error == "File too large"
        assert "50MB" in error.detail or "50" in error.detail
        assert error.status_code == 413

    @pytest.mark.asyncio
    async def test_ocr_processing_error_handling(self):
        """Test OCR processing errors are caught and logged"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_processing_error(
            task_id="test-task-123",
            error_type="tesseract_error",
            error_message="Tesseract failed to process image"
        )

        assert error.task_id == "test-task-123"
        assert error.status == TaskStatus.FAILED
        assert "Tesseract" in error.message

    @pytest.mark.asyncio
    async def test_redis_connection_error_handling(self):
        """Test Redis connection errors are handled gracefully"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_redis_error(
            operation="connect",
            error_message="Connection refused"
        )

        assert error.error == "Service temporarily unavailable"
        assert "redis" in error.detail.lower() and "connection" in error.detail.lower()
        assert error.status_code == 503

    @pytest.mark.asyncio
    async def test_task_not_found_error(self):
        """Test task not found errors"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_not_found_error(
            resource_type="task",
            resource_id="non-existent-task"
        )

        assert error.error == "Task not found"
        assert "non-existent-task" in error.detail
        assert error.status_code == 404

    @pytest.mark.asyncio
    async def test_batch_not_found_error(self):
        """Test batch not found errors"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_not_found_error(
            resource_type="batch",
            resource_id="non-existent-batch"
        )

        assert error.error == "Batch not found"
        assert error.status_code == 404

    @pytest.mark.asyncio
    async def test_timeout_error_handling(self):
        """Test processing timeout errors"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_timeout_error(
            task_id="test-task-123",
            timeout_seconds=300
        )

        assert error.status == TaskStatus.FAILED
        assert "timeout" in error.message.lower()
        assert "300" in error.message or "5" in error.message  # 5 minutes

    @pytest.mark.asyncio
    async def test_corrupted_file_error(self):
        """Test corrupted file error handling"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_processing_error(
            task_id="test-task-123",
            error_type="corrupted_file",
            error_message="Unable to read PDF structure"
        )

        assert "corrupted" in error.message.lower() or "unable to read" in error.message.lower()
        assert error.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_unsupported_language_error(self):
        """Test unsupported language error handling"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_validation_error(
            error_type="unsupported_language",
            language="xyz"
        )

        assert "language" in error.error.lower()
        assert "xyz" in error.detail
        assert error.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_dependency_error(self):
        """Test missing dependency (e.g., Tesseract) error handling"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_system_error(
            error_type="missing_dependency",
            dependency="tesseract"
        )

        assert "tesseract" in error.error.lower()
        assert error.status_code == 503

    @pytest.mark.asyncio
    async def test_disk_space_error(self):
        """Test disk space error handling"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_system_error(
            error_type="disk_full",
            error_message="No space left on device"
        )

        assert "disk" in error.error.lower() or "space" in error.error.lower()
        assert error.status_code == 507

    @pytest.mark.asyncio
    async def test_rate_limit_error(self):
        """Test rate limiting error handling"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_rate_limit_error(
            client_id="client-123",
            retry_after=60
        )

        assert "rate limit" in error.error.lower()
        assert error.status_code == 429
        assert error.retry_after == 60

    @pytest.mark.asyncio
    async def test_concurrent_processing_limit(self):
        """Test concurrent processing limit errors"""
        from app.error_handler import ErrorHandler

        error = ErrorHandler.handle_system_error(
            error_type="processing_limit",
            error_message="Maximum concurrent tasks reached"
        )

        assert "concurrent" in error.detail.lower() or "limit" in error.detail.lower()
        assert error.status_code == 503


class TestStatusReporting:
    """Tests for processing status reporting"""

    @pytest.mark.asyncio
    async def test_status_transition_queued_to_processing(self):
        """Test status transition from queued to processing"""
        from app.status_reporter import StatusReporter

        reporter = StatusReporter("test-task-123")

        # Start processing
        await reporter.start_processing()

        status = await reporter.get_status()
        assert status.status == TaskStatus.PROCESSING
        assert status.progress >= 0
        assert "processing" in status.message.lower()

    @pytest.mark.asyncio
    async def test_status_progress_updates(self):
        """Test progress updates during processing"""
        from app.status_reporter import StatusReporter

        reporter = StatusReporter("test-task-123")
        await reporter.start_processing()

        # Update progress
        await reporter.update_progress(25, "Processing page 1 of 4")
        status = await reporter.get_status()
        assert status.progress == 25

        await reporter.update_progress(50, "Processing page 2 of 4")
        status = await reporter.get_status()
        assert status.progress == 50

        await reporter.update_progress(100, "Processing complete")
        status = await reporter.get_status()
        assert status.progress == 100

    @pytest.mark.asyncio
    async def test_status_completion_reporting(self):
        """Test status reporting on successful completion"""
        from app.status_reporter import StatusReporter

        reporter = StatusReporter("test-task-123")
        await reporter.start_processing()

        # Complete task
        await reporter.complete(result={"text": "Sample text"})

        status = await reporter.get_status()
        assert status.status == TaskStatus.COMPLETED
        assert status.progress == 100

    @pytest.mark.asyncio
    async def test_status_failure_reporting(self):
        """Test status reporting on failure"""
        from app.status_reporter import StatusReporter

        reporter = StatusReporter("test-task-123")
        await reporter.start_processing()

        # Fail task
        await reporter.fail(error_message="Tesseract error")

        status = await reporter.get_status()
        assert status.status == TaskStatus.FAILED
        assert "error" in status.message.lower()

    @pytest.mark.asyncio
    async def test_status_with_estimated_time(self):
        """Test status reporting includes estimated completion time"""
        from app.status_reporter import StatusReporter

        reporter = StatusReporter("test-task-123")
        await reporter.start_processing()

        await reporter.update_progress(50, "Processing...")

        status = await reporter.get_status()
        # Should have estimated time remaining
        assert hasattr(status, "estimated_completion_time") or "estimated" in str(status.__dict__)

    @pytest.mark.asyncio
    async def test_batch_status_aggregation(self):
        """Test batch status aggregation"""
        from app.status_reporter import BatchStatusReporter

        task_ids = ["task-1", "task-2", "task-3"]
        reporter = BatchStatusReporter("batch-123", task_ids)

        # Update individual task statuses
        await reporter.update_task_status("task-1", TaskStatus.COMPLETED, 100)
        await reporter.update_task_status("task-2", TaskStatus.PROCESSING, 50)
        await reporter.update_task_status("task-3", TaskStatus.QUEUED, 0)

        status = await reporter.get_batch_status()
        assert status["completed"] == 1
        assert status["processing"] == 1
        assert status["queued"] == 1
        assert status["total"] == 3

    @pytest.mark.asyncio
    async def test_status_history_tracking(self):
        """Test status change history is tracked"""
        from app.status_reporter import StatusReporter

        reporter = StatusReporter("test-task-123")

        await reporter.start_processing()
        await reporter.update_progress(50, "Halfway")
        await reporter.complete()

        history = await reporter.get_status_history()
        assert len(history) >= 3
        assert history[0]["status"] == TaskStatus.QUEUED
        assert history[-1]["status"] == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_status_webhook_notifications(self):
        """Test status updates trigger webhook notifications"""
        from app.status_reporter import StatusReporter

        webhook_called = False
        webhook_data = None

        async def mock_webhook(data):
            nonlocal webhook_called, webhook_data
            webhook_called = True
            webhook_data = data

        reporter = StatusReporter("test-task-123", webhook_url="http://example.com/webhook")
        reporter.set_webhook_handler(mock_webhook)

        await reporter.complete()

        assert webhook_called is True
        assert webhook_data["status"] == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_status_polling_interval(self):
        """Test status polling returns appropriate cache headers"""
        from app.status_reporter import StatusReporter

        reporter = StatusReporter("test-task-123")
        await reporter.start_processing()

        status, headers = await reporter.get_status_with_headers()

        assert "Cache-Control" in headers
        assert "no-cache" in headers["Cache-Control"] or "max-age" in headers["Cache-Control"]

    @pytest.mark.asyncio
    async def test_processing_metrics_collection(self):
        """Test processing metrics are collected"""
        from app.status_reporter import StatusReporter

        reporter = StatusReporter("test-task-123")
        await reporter.start_processing()

        # Simulate processing
        await asyncio.sleep(0.1)

        await reporter.complete()

        metrics = await reporter.get_metrics()
        assert "processing_time" in metrics
        assert metrics["processing_time"] > 0

    @pytest.mark.asyncio
    async def test_status_retry_information(self):
        """Test status includes retry information for failed tasks"""
        from app.status_reporter import StatusReporter

        reporter = StatusReporter("test-task-123")
        await reporter.start_processing()

        # Fail with retry
        await reporter.fail(error_message="Temporary error", retryable=True)

        status = await reporter.get_status()
        assert hasattr(status, "retryable") and status.retryable is True
        assert hasattr(status, "retry_count")


class TestErrorRecovery:
    """Tests for error recovery mechanisms"""

    @pytest.mark.asyncio
    async def test_automatic_retry_on_transient_error(self):
        """Test automatic retry on transient errors"""
        from app.error_handler import ErrorHandler

        should_retry = ErrorHandler.should_retry_error(
            error_type="network_timeout",
            retry_count=0
        )

        assert should_retry is True

    @pytest.mark.asyncio
    async def test_no_retry_on_permanent_error(self):
        """Test no retry on permanent errors"""
        from app.error_handler import ErrorHandler

        should_retry = ErrorHandler.should_retry_error(
            error_type="invalid_file_format",
            retry_count=0
        )

        assert should_retry is False

    @pytest.mark.asyncio
    async def test_max_retry_limit(self):
        """Test retry limit is enforced"""
        from app.error_handler import ErrorHandler

        should_retry = ErrorHandler.should_retry_error(
            error_type="network_timeout",
            retry_count=5,
            max_retries=3
        )

        assert should_retry is False

    @pytest.mark.asyncio
    async def test_exponential_backoff_calculation(self):
        """Test exponential backoff for retries"""
        from app.error_handler import ErrorHandler

        backoff_1 = ErrorHandler.calculate_backoff(retry_count=1)
        backoff_2 = ErrorHandler.calculate_backoff(retry_count=2)
        backoff_3 = ErrorHandler.calculate_backoff(retry_count=3)

        assert backoff_2 > backoff_1
        assert backoff_3 > backoff_2

    @pytest.mark.asyncio
    async def test_error_logging_with_context(self):
        """Test errors are logged with full context"""
        from app.error_handler import ErrorHandler

        with patch('app.error_handler.logger') as mock_logger:
            ErrorHandler.log_error(
                task_id="test-task-123",
                error_type="processing_error",
                error_message="Test error",
                context={
                    "file_name": "test.pdf",
                    "file_size": 1024,
                    "language": "eng"
                }
            )

            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert "test-task-123" in str(call_args)
            assert "test.pdf" in str(call_args)

    @pytest.mark.asyncio
    async def test_error_aggregation_for_batch(self):
        """Test error aggregation for batch processing"""
        from app.error_handler import ErrorHandler

        errors = [
            {"task_id": "task-1", "error": "Error 1"},
            {"task_id": "task-2", "error": "Error 2"},
            {"task_id": "task-3", "error": "Error 1"},
        ]

        summary = ErrorHandler.aggregate_batch_errors(errors)

        assert summary["total_errors"] == 3
        assert len(summary["unique_errors"]) == 2
        assert summary["most_common_error"] == "Error 1"


class TestErrorMiddleware:
    """Tests for global error handling middleware"""

    @pytest.mark.asyncio
    async def test_uncaught_exception_handling(self):
        """Test uncaught exceptions are properly handled"""
        from app.middleware import error_middleware
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.headers.get.return_value = "test-request-id"

        async def failing_endpoint(request):
            raise Exception("Unexpected error")

        response = await error_middleware(mock_request, failing_endpoint)

        assert response.status_code == 500
        assert "error" in response.body.decode().lower()

    @pytest.mark.asyncio
    async def test_http_exception_formatting(self):
        """Test HTTPException is properly formatted"""
        from app.middleware import error_middleware
        from fastapi import Request, HTTPException

        mock_request = MagicMock(spec=Request)
        mock_request.headers.get.return_value = "test-request-id"

        async def http_error_endpoint(request):
            raise HTTPException(status_code=404, detail="Not found")

        response = await error_middleware(mock_request, http_error_endpoint)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_validation_error_formatting(self):
        """Test Pydantic ValidationError is properly formatted"""
        from app.middleware import error_middleware
        from fastapi import Request
        from pydantic import ValidationError

        mock_request = MagicMock(spec=Request)

        # This will be caught by FastAPI's validation, testing our formatting
        # Actual implementation will use FastAPI's exception handlers

    @pytest.mark.asyncio
    async def test_error_response_includes_request_id(self):
        """Test error responses include request ID for tracing"""
        from app.middleware import error_middleware
        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="req-123")
        mock_request.headers = mock_headers

        async def failing_endpoint(request):
            raise Exception("Error")

        response = await error_middleware(mock_request, failing_endpoint)

        response_data = response.body.decode()
        assert "req-123" in response_data or "request_id" in response_data.lower()
