"""
Task manager for OCR processing
Simple in-memory task storage (will be replaced with Redis in later tasks)
"""
import uuid
from datetime import datetime
from typing import Dict, Optional, List
from .models import TaskStatus, TaskStatusResponse, OCRResult


class TaskManager:
    """Manages OCR tasks and their status"""

    def __init__(self):
        self.tasks: Dict[str, dict] = {}
        self.batches: Dict[str, dict] = {}
        self.results: Dict[str, OCRResult] = {}

    def create_task(self, language: Optional[str] = "eng") -> str:
        """Create a new OCR task and return task ID"""
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "task_id": task_id,
            "status": TaskStatus.QUEUED,
            "progress": 0,
            "message": "Task queued for processing",
            "language": language,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        return task_id

    def create_batch(self, task_ids: List[str]) -> str:
        """Create a new batch and return batch ID"""
        batch_id = str(uuid.uuid4())
        self.batches[batch_id] = {
            "batch_id": batch_id,
            "task_ids": task_ids,
            "total": len(task_ids),
            "created_at": datetime.utcnow(),
        }
        return batch_id

    def get_task_status(self, task_id: str) -> Optional[TaskStatusResponse]:
        """Get status of a task"""
        if task_id not in self.tasks:
            return None

        task = self.tasks[task_id]
        return TaskStatusResponse(**task)

    def get_batch_status(self, batch_id: str) -> Optional[dict]:
        """Get status of a batch"""
        if batch_id not in self.batches:
            return None

        batch = self.batches[batch_id]
        task_ids = batch["task_ids"]

        # Count tasks by status
        completed = sum(1 for tid in task_ids if self.tasks.get(tid, {}).get("status") == TaskStatus.COMPLETED)
        failed = sum(1 for tid in task_ids if self.tasks.get(tid, {}).get("status") == TaskStatus.FAILED)
        processing = sum(1 for tid in task_ids if self.tasks.get(tid, {}).get("status") == TaskStatus.PROCESSING)
        queued = sum(1 for tid in task_ids if self.tasks.get(tid, {}).get("status") == TaskStatus.QUEUED)

        return {
            "batch_id": batch_id,
            "total": batch["total"],
            "completed": completed,
            "failed": failed,
            "processing": processing,
            "queued": queued,
        }

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[int] = None,
        message: Optional[str] = None
    ) -> bool:
        """Update task status"""
        if task_id not in self.tasks:
            return False

        self.tasks[task_id]["status"] = status
        self.tasks[task_id]["updated_at"] = datetime.utcnow()

        if progress is not None:
            self.tasks[task_id]["progress"] = progress
        if message is not None:
            self.tasks[task_id]["message"] = message

        return True

    def store_result(self, task_id: str, result: OCRResult) -> bool:
        """Store OCR result for a task"""
        if task_id not in self.tasks:
            return False

        self.results[task_id] = result
        self.update_task_status(task_id, TaskStatus.COMPLETED, 100, "Processing completed")
        return True

    def get_result(self, task_id: str) -> Optional[OCRResult]:
        """Get OCR result for a task"""
        return self.results.get(task_id)

    def task_exists(self, task_id: str) -> bool:
        """Check if task exists"""
        return task_id in self.tasks

    def batch_exists(self, batch_id: str) -> bool:
        """Check if batch exists"""
        return batch_id in self.batches


# Global task manager instance
task_manager = TaskManager()
