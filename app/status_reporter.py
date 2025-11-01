"""
Status reporting for OCR processing tasks
Tracks task progress, provides status updates, and manages webhooks
"""
import logging
from typing import Optional, Dict, List, Any, Callable
from datetime import datetime, timedelta
import asyncio
import httpx

from .models import TaskStatus, TaskStatusResponse


logger = logging.getLogger(__name__)


class StatusReporter:
    """
    Manages status reporting for individual OCR tasks

    Features:
    - Progress tracking
    - Status transitions
    - Webhook notifications
    - Status history
    - Processing metrics
    """

    def __init__(
        self,
        task_id: str,
        webhook_url: Optional[str] = None,
        redis_queue_manager=None
    ):
        """
        Initialize status reporter

        Args:
            task_id: Task identifier
            webhook_url: Optional webhook URL for status notifications
            redis_queue_manager: Optional Redis queue manager for persistence
        """
        self.task_id = task_id
        self.webhook_url = webhook_url
        self.redis_queue_manager = redis_queue_manager
        self.webhook_handler: Optional[Callable] = None

        self.status = TaskStatus.QUEUED
        self.progress = 0
        self.message = "Task queued"
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

        self.status_history: List[Dict[str, Any]] = []
        self._add_to_history(TaskStatus.QUEUED, "Task created")

    def _add_to_history(self, status: TaskStatus, message: str):
        """Add status change to history"""
        self.status_history.append({
            "status": status,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "progress": self.progress
        })

    async def start_processing(self):
        """Mark task as processing"""
        self.status = TaskStatus.PROCESSING
        self.progress = 0
        self.message = "Processing started"
        self.started_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

        self._add_to_history(TaskStatus.PROCESSING, "Processing started")

        # Update in Redis if available
        if self.redis_queue_manager:
            await self.redis_queue_manager.update_task_status(
                self.task_id,
                TaskStatus.PROCESSING,
                progress=0,
                message="Processing started"
            )

        # Send webhook notification
        await self._send_webhook_notification()

        logger.info(f"Task {self.task_id} started processing")

    async def update_progress(self, progress: int, message: str):
        """
        Update task progress

        Args:
            progress: Progress percentage (0-100)
            message: Status message
        """
        self.progress = max(0, min(100, progress))  # Clamp to 0-100
        self.message = message
        self.updated_at = datetime.utcnow()

        # Update in Redis if available
        if self.redis_queue_manager:
            await self.redis_queue_manager.update_task_status(
                self.task_id,
                self.status,
                progress=self.progress,
                message=message
            )

        logger.info(f"Task {self.task_id} progress: {self.progress}% - {message}")

    async def complete(self, result: Optional[Dict[str, Any]] = None):
        """
        Mark task as completed

        Args:
            result: Optional result data
        """
        self.status = TaskStatus.COMPLETED
        self.progress = 100
        self.message = "Processing completed successfully"
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

        self._add_to_history(TaskStatus.COMPLETED, "Processing completed")

        # Update in Redis if available
        if self.redis_queue_manager:
            await self.redis_queue_manager.update_task_status(
                self.task_id,
                TaskStatus.COMPLETED,
                progress=100,
                message="Processing completed"
            )

        # Send webhook notification
        await self._send_webhook_notification()

        logger.info(f"Task {self.task_id} completed successfully")

    async def fail(self, error_message: str, retryable: bool = False):
        """
        Mark task as failed

        Args:
            error_message: Error message
            retryable: Whether the error is retryable
        """
        self.status = TaskStatus.FAILED
        self.message = f"Processing failed: {error_message}"
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.retryable = retryable

        self._add_to_history(TaskStatus.FAILED, error_message)

        # Update in Redis if available
        if self.redis_queue_manager:
            await self.redis_queue_manager.update_task_status(
                self.task_id,
                TaskStatus.FAILED,
                message=f"Failed: {error_message}"
            )

        # Send webhook notification
        await self._send_webhook_notification()

        logger.error(f"Task {self.task_id} failed: {error_message}")

    async def get_status(self) -> TaskStatusResponse:
        """
        Get current task status

        Returns:
            TaskStatusResponse with current status
        """
        # Calculate estimated completion time if processing
        estimated_completion_time = None
        if self.status == TaskStatus.PROCESSING and self.progress > 0:
            elapsed = (datetime.utcnow() - self.started_at).total_seconds()
            estimated_total = (elapsed / self.progress) * 100
            remaining = estimated_total - elapsed
            estimated_completion_time = (datetime.utcnow() + timedelta(seconds=remaining)).isoformat()

        status = TaskStatusResponse(
            task_id=self.task_id,
            status=self.status,
            progress=self.progress,
            message=self.message,
            created_at=self.created_at.isoformat(),
            updated_at=self.updated_at.isoformat()
        )

        # Add estimated completion time if available
        if estimated_completion_time:
            status.estimated_completion_time = estimated_completion_time

        # Add retry information if failed
        if self.status == TaskStatus.FAILED and hasattr(self, 'retryable'):
            status.retryable = self.retryable
            status.retry_count = getattr(self, 'retry_count', 0)

        return status

    async def get_status_with_headers(self) -> tuple[TaskStatusResponse, Dict[str, str]]:
        """
        Get status with appropriate HTTP headers

        Returns:
            Tuple of (status, headers)
        """
        status = await self.get_status()

        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }

        # Add polling interval suggestion
        if status.status in [TaskStatus.QUEUED, TaskStatus.PROCESSING]:
            headers["X-Poll-Interval"] = "5"  # Suggest polling every 5 seconds

        return status, headers

    async def get_status_history(self) -> List[Dict[str, Any]]:
        """
        Get status change history

        Returns:
            List of status changes with timestamps
        """
        return self.status_history

    async def get_metrics(self) -> Dict[str, Any]:
        """
        Get processing metrics

        Returns:
            Dictionary of metrics
        """
        metrics = {
            "task_id": self.task_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }

        if self.started_at:
            metrics["started_at"] = self.started_at.isoformat()

        if self.completed_at:
            metrics["completed_at"] = self.completed_at.isoformat()

            # Calculate processing time
            if self.started_at:
                processing_time = (self.completed_at - self.started_at).total_seconds()
                metrics["processing_time"] = processing_time

        return metrics

    def set_webhook_handler(self, handler: Callable):
        """
        Set custom webhook handler for testing

        Args:
            handler: Async callable that accepts webhook data
        """
        self.webhook_handler = handler

    async def _send_webhook_notification(self):
        """Send webhook notification if configured"""
        if not self.webhook_url and not self.webhook_handler:
            return

        webhook_data = {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "timestamp": datetime.utcnow().isoformat()
        }

        try:
            if self.webhook_handler:
                # Use custom handler (for testing)
                await self.webhook_handler(webhook_data)
            elif self.webhook_url:
                # Send HTTP POST to webhook URL
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.webhook_url,
                        json=webhook_data,
                        timeout=10.0
                    )
                    response.raise_for_status()
                    logger.info(f"Webhook notification sent for task {self.task_id}")
        except Exception as e:
            logger.warning(f"Failed to send webhook notification for task {self.task_id}: {e}")


class BatchStatusReporter:
    """
    Manages status reporting for batch processing

    Aggregates status from multiple tasks
    """

    def __init__(
        self,
        batch_id: str,
        task_ids: List[str],
        redis_queue_manager=None
    ):
        """
        Initialize batch status reporter

        Args:
            batch_id: Batch identifier
            task_ids: List of task identifiers in batch
            redis_queue_manager: Optional Redis queue manager
        """
        self.batch_id = batch_id
        self.task_ids = task_ids
        self.redis_queue_manager = redis_queue_manager

        # Track individual task statuses
        self.task_statuses: Dict[str, TaskStatus] = {
            task_id: TaskStatus.QUEUED for task_id in task_ids
        }
        self.task_progress: Dict[str, int] = {
            task_id: 0 for task_id in task_ids
        }

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: int
    ):
        """
        Update status of individual task in batch

        Args:
            task_id: Task identifier
            status: New status
            progress: Progress percentage
        """
        if task_id in self.task_statuses:
            self.task_statuses[task_id] = status
            self.task_progress[task_id] = progress

    async def get_batch_status(self) -> Dict[str, Any]:
        """
        Get aggregated batch status

        Returns:
            Dictionary with batch status information
        """
        completed = sum(1 for s in self.task_statuses.values() if s == TaskStatus.COMPLETED)
        failed = sum(1 for s in self.task_statuses.values() if s == TaskStatus.FAILED)
        processing = sum(1 for s in self.task_statuses.values() if s == TaskStatus.PROCESSING)
        queued = sum(1 for s in self.task_statuses.values() if s == TaskStatus.QUEUED)

        return {
            "batch_id": self.batch_id,
            "total": len(self.task_ids),
            "completed": completed,
            "failed": failed,
            "processing": processing,
            "queued": queued,
            "progress_percentage": (completed / len(self.task_ids) * 100) if self.task_ids else 0
        }
