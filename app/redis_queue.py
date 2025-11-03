"""
Redis-based queue manager for OCR processing
Replaces in-memory task storage with persistent Redis storage
"""
import uuid
import json
from redis import asyncio as aioredis
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import logging
from .models import TaskStatus, TaskStatusResponse, OCRResult

logger = logging.getLogger(__name__)


class RedisQueueManager:
    """
    Manages OCR tasks using Redis for persistence and queuing

    Features:
    - Persistent task storage
    - Priority queue support (high, normal, low)
    - Task status tracking
    - Result storage with TTL
    - Batch operations
    - Retry mechanism
    """

    # Redis key prefixes
    TASK_PREFIX = "task:"
    RESULT_PREFIX = "result:"
    BATCH_PREFIX = "batch:"
    QUEUE_PREFIX = "queue:"

    # Queue names by priority
    QUEUE_HIGH = "queue:high"
    QUEUE_NORMAL = "queue:normal"
    QUEUE_LOW = "queue:low"

    # Dead letter queue for permanently failed tasks
    DEAD_LETTER_QUEUE = "queue:dead_letter"

    # Configuration
    RESULT_TTL = 86400  # Results expire after 24 hours
    MAX_RETRIES = 3  # Maximum retry attempts for failed tasks

    def __init__(self, redis_url: str):
        """
        Initialize Redis queue manager

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
        """
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None

    async def connect(self):
        """Establish connection to Redis"""
        try:
            self.redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False
            )
            # Test connection
            await self.redis.ping()
            logger.info(f"Connected to Redis: {self.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            logger.info("Disconnected from Redis")

    async def create_task(
        self,
        language: Optional[str] = "eng",
        priority: str = "normal",
        file_path: Optional[str] = None,
        filename: Optional[str] = None,
        document_id: Optional[str] = None
    ) -> str:
        """
        Create a new OCR task and add to queue

        Args:
            language: OCR language (default: eng)
            priority: Task priority (high, normal, low)
            file_path: Path to uploaded file
            filename: Original filename
            document_id: Backend document ID for webhook callbacks

        Returns:
            task_id: Unique task identifier
        """
        task_id = str(uuid.uuid4())
        now = datetime.utcnow()

        task_data = {
            "task_id": task_id,
            "status": TaskStatus.QUEUED.value,  # Store enum value, not enum itself
            "progress": 0,
            "message": "Task queued for processing",
            "language": language,
            "priority": priority,
            "retry_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        # Add optional fields if provided
        if file_path:
            task_data["file_path"] = file_path
        if filename:
            task_data["filename"] = filename
        if document_id:
            task_data["document_id"] = document_id

        # Store task data in Redis hash
        task_key = f"{self.TASK_PREFIX}{task_id}"
        await self.redis.hset(
            task_key,
            mapping={k: str(v) for k, v in task_data.items()}
        )

        # Add task to appropriate priority queue
        queue_name = self._get_queue_name(priority)
        await self.redis.lpush(queue_name, task_id)

        logger.info(f"Created task {task_id} with priority {priority}")
        return task_id

    def _get_queue_name(self, priority: str) -> str:
        """Get queue name based on priority"""
        priority_queues = {
            "high": self.QUEUE_HIGH,
            "normal": self.QUEUE_NORMAL,
            "low": self.QUEUE_LOW,
        }
        return priority_queues.get(priority, self.QUEUE_NORMAL)

    async def dequeue_task(self, priority: Optional[str] = None) -> Optional[str]:
        """
        Dequeue next task from queue and set task_started_at timestamp

        Checks queues in priority order: high -> normal -> low

        Args:
            priority: Specific priority queue to check (optional)

        Returns:
            task_id or None if no tasks available
        """
        task_id_bytes = None

        if priority:
            # Check specific priority queue
            queue_name = self._get_queue_name(priority)
            task_id_bytes = await self.redis.rpop(queue_name)
        else:
            # Check all queues in priority order
            for queue in [self.QUEUE_HIGH, self.QUEUE_NORMAL, self.QUEUE_LOW]:
                task_id_bytes = await self.redis.rpop(queue)
                if task_id_bytes:
                    break

        if not task_id_bytes:
            return None

        task_id = task_id_bytes.decode()

        # Set task_started_at timestamp when task is dequeued
        task_key = f"{self.TASK_PREFIX}{task_id}"
        await self.redis.hset(
            task_key,
            "task_started_at",
            datetime.utcnow().isoformat()
        )

        logger.info(f"Dequeued task {task_id} and set task_started_at timestamp")
        return task_id

    async def get_task_status(self, task_id: str) -> Optional[TaskStatusResponse]:
        """
        Get status of a task

        Args:
            task_id: Task identifier

        Returns:
            TaskStatusResponse or None if task not found
        """
        task_key = f"{self.TASK_PREFIX}{task_id}"
        task_data = await self.redis.hgetall(task_key)

        if not task_data:
            return None

        # Decode bytes and convert to proper types
        decoded_data = {}
        for key, value in task_data.items():
            key_str = key.decode() if isinstance(key, bytes) else key
            value_str = value.decode() if isinstance(value, bytes) else value
            decoded_data[key_str] = value_str

        # Convert string values to proper types
        return TaskStatusResponse(
            task_id=decoded_data["task_id"],
            status=TaskStatus(decoded_data["status"]),
            progress=int(decoded_data["progress"]),
            message=decoded_data["message"],
            created_at=decoded_data.get("created_at"),
            updated_at=decoded_data.get("updated_at"),
        )

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[int] = None,
        message: Optional[str] = None
    ) -> bool:
        """
        Update task status

        Args:
            task_id: Task identifier
            status: New status
            progress: Progress percentage (0-100)
            message: Status message

        Returns:
            True if updated, False if task not found
        """
        task_key = f"{self.TASK_PREFIX}{task_id}"

        # Check if task exists
        exists = await self.redis.exists(task_key)
        if not exists:
            return False

        # Update fields
        update_data = {
            "status": status.value if isinstance(status, TaskStatus) else status,
            "updated_at": datetime.utcnow().isoformat(),
        }

        if progress is not None:
            update_data["progress"] = progress

        if message is not None:
            update_data["message"] = message

        await self.redis.hset(
            task_key,
            mapping={k: str(v) for k, v in update_data.items()}
        )

        logger.info(f"Updated task {task_id}: {status}")
        return True

    async def store_result(self, task_id: str, result: OCRResult) -> bool:
        """
        Store OCR result for a task

        Results are stored with TTL and expire after configured time

        Args:
            task_id: Task identifier
            result: OCR processing result

        Returns:
            True if stored successfully
        """
        result_key = f"{self.RESULT_PREFIX}{task_id}"

        # Convert result to JSON
        result_json = result.model_dump_json()

        # Store with expiration
        await self.redis.setex(
            result_key,
            self.RESULT_TTL,
            result_json
        )

        # Update task status and set completed_at timestamp
        task_key = f"{self.TASK_PREFIX}{task_id}"
        await self.redis.hset(
            task_key,
            mapping={
                "status": TaskStatus.COMPLETED,
                "progress": "100",
                "message": "Processing completed",
                "completed_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
        )

        logger.info(f"Stored result for task {task_id}")
        return True

    async def get_result(self, task_id: str) -> Optional[OCRResult]:
        """
        Get OCR result for a task

        Args:
            task_id: Task identifier

        Returns:
            OCRResult or None if not found or expired
        """
        result_key = f"{self.RESULT_PREFIX}{task_id}"
        result_json = await self.redis.get(result_key)

        if not result_json:
            return None

        # Decode and parse JSON
        if isinstance(result_json, bytes):
            result_json = result_json.decode()

        result_data = json.loads(result_json)
        return OCRResult(**result_data)

    async def get_result_ttl(self, task_id: str) -> int:
        """
        Get remaining TTL for a result

        Args:
            task_id: Task identifier

        Returns:
            TTL in seconds, -1 if no expiration, -2 if key doesn't exist
        """
        result_key = f"{self.RESULT_PREFIX}{task_id}"
        return await self.redis.ttl(result_key)

    async def create_batch(self, task_ids: List[str]) -> str:
        """
        Create a batch of tasks

        Args:
            task_ids: List of task identifiers

        Returns:
            batch_id: Unique batch identifier
        """
        batch_id = str(uuid.uuid4())
        now = datetime.utcnow()

        batch_data = {
            "batch_id": batch_id,
            "task_ids": json.dumps(task_ids),
            "total": len(task_ids),
            "created_at": now.isoformat(),
        }

        # Store batch data
        batch_key = f"{self.BATCH_PREFIX}{batch_id}"
        await self.redis.hset(
            batch_key,
            mapping={k: str(v) for k, v in batch_data.items()}
        )

        logger.info(f"Created batch {batch_id} with {len(task_ids)} tasks")
        return batch_id

    async def get_batch_status(self, batch_id: str) -> Optional[Dict]:
        """
        Get status of a batch

        Args:
            batch_id: Batch identifier

        Returns:
            Dictionary with batch status or None if not found
        """
        batch_key = f"{self.BATCH_PREFIX}{batch_id}"
        batch_data = await self.redis.hgetall(batch_key)

        if not batch_data:
            return None

        # Decode batch data
        decoded_data = {}
        for key, value in batch_data.items():
            key_str = key.decode() if isinstance(key, bytes) else key
            value_str = value.decode() if isinstance(value, bytes) else value
            decoded_data[key_str] = value_str

        # Parse task IDs
        task_ids = json.loads(decoded_data["task_ids"])

        # Count tasks by status
        completed = 0
        failed = 0
        processing = 0
        queued = 0

        for task_id in task_ids:
            task_status = await self.get_task_status(task_id)
            if task_status:
                if task_status.status == TaskStatus.COMPLETED:
                    completed += 1
                elif task_status.status == TaskStatus.FAILED:
                    failed += 1
                elif task_status.status == TaskStatus.PROCESSING:
                    processing += 1
                elif task_status.status == TaskStatus.QUEUED:
                    queued += 1

        return {
            "batch_id": decoded_data["batch_id"],
            "total": int(decoded_data["total"]),
            "completed": completed,
            "failed": failed,
            "processing": processing,
            "queued": queued,
        }

    async def get_queue_length(self, priority: Optional[str] = None) -> int:
        """
        Get length of queue

        Args:
            priority: Specific priority queue (optional, defaults to all)

        Returns:
            Number of tasks in queue(s)
        """
        if priority:
            queue_name = self._get_queue_name(priority)
            return await self.redis.llen(queue_name)

        # Sum all queues
        total = 0
        for queue in [self.QUEUE_HIGH, self.QUEUE_NORMAL, self.QUEUE_LOW]:
            total += await self.redis.llen(queue)

        return total

    async def get_queue_stats(self) -> Dict:
        """
        Get statistics for all queues

        Returns:
            Dictionary with queue statistics
        """
        high_length = await self.redis.llen(self.QUEUE_HIGH)
        normal_length = await self.redis.llen(self.QUEUE_NORMAL)
        low_length = await self.redis.llen(self.QUEUE_LOW)

        return {
            "high_priority": high_length,
            "normal_queue": normal_length,
            "low_priority": low_length,
            "total": high_length + normal_length + low_length,
        }

    async def retry_task(
        self,
        task_id: str,
        max_retries: Optional[int] = None
    ) -> bool:
        """
        Retry a failed task

        Args:
            task_id: Task identifier
            max_retries: Maximum retry attempts (defaults to MAX_RETRIES)

        Returns:
            True if task was re-queued, False if max retries exceeded
        """
        if max_retries is None:
            max_retries = self.MAX_RETRIES

        task_key = f"{self.TASK_PREFIX}{task_id}"
        task_data = await self.redis.hgetall(task_key)

        if not task_data:
            return False

        # Decode retry count
        retry_count_bytes = task_data.get(b"retry_count", b"0")
        retry_count = int(retry_count_bytes.decode() if isinstance(retry_count_bytes, bytes) else retry_count_bytes)

        # Check if task is already in dead letter queue
        in_dlq_bytes = task_data.get(b"in_dead_letter_queue", b"false")
        in_dlq = (in_dlq_bytes.decode() if isinstance(in_dlq_bytes, bytes) else in_dlq_bytes) == "true"

        if in_dlq:
            logger.warning(f"Task {task_id} is in dead letter queue and cannot be retried")
            return False

        if retry_count >= max_retries:
            logger.warning(f"Task {task_id} exceeded max retries ({max_retries})")
            # Move to dead letter queue
            await self.move_to_dead_letter_queue(
                task_id,
                f"Max retries exceeded ({retry_count}/{max_retries})"
            )
            return False

        # Increment retry count
        await self.redis.hset(task_key, "retry_count", retry_count + 1)

        # Reset status and re-queue
        await self.update_task_status(
            task_id,
            TaskStatus.QUEUED,
            progress=0,
            message=f"Retrying (attempt {retry_count + 1})"
        )

        # Get priority and re-queue
        priority_bytes = task_data.get(b"priority", b"normal")
        priority = priority_bytes.decode() if isinstance(priority_bytes, bytes) else priority_bytes
        queue_name = self._get_queue_name(priority)
        await self.redis.lpush(queue_name, task_id)

        logger.info(f"Retrying task {task_id} (attempt {retry_count + 1})")
        return True

    async def cleanup_task(self, task_id: str) -> bool:
        """
        Clean up task and result data

        Args:
            task_id: Task identifier

        Returns:
            True if cleaned up successfully
        """
        task_key = f"{self.TASK_PREFIX}{task_id}"
        result_key = f"{self.RESULT_PREFIX}{task_id}"

        # Delete both task and result
        await self.redis.delete(task_key, result_key)

        logger.info(f"Cleaned up task {task_id}")
        return True

    async def task_exists(self, task_id: str) -> bool:
        """
        Check if task exists

        Args:
            task_id: Task identifier

        Returns:
            True if task exists
        """
        task_key = f"{self.TASK_PREFIX}{task_id}"
        return await self.redis.exists(task_key) > 0

    async def batch_exists(self, batch_id: str) -> bool:
        """
        Check if batch exists

        Args:
            batch_id: Batch identifier

        Returns:
            True if batch exists
        """
        batch_key = f"{self.BATCH_PREFIX}{batch_id}"
        return await self.redis.exists(batch_key) > 0

    async def get_task_file_path(self, task_id: str) -> Optional[str]:
        """
        Get file path for a task

        Args:
            task_id: Task identifier

        Returns:
            File path or None if not set
        """
        task_key = f"{self.TASK_PREFIX}{task_id}"
        file_path = await self.redis.hget(task_key, "file_path")

        if file_path:
            return file_path.decode() if isinstance(file_path, bytes) else file_path

        return None

    async def find_stuck_tasks(
        self,
        timeout_minutes: int = 30,
        alert_threshold: Optional[int] = 10
    ) -> List[str]:
        """
        Find tasks that are stuck in PROCESSING status beyond timeout threshold

        Args:
            timeout_minutes: Timeout threshold in minutes (default: 30)
            alert_threshold: Trigger warning if stuck count exceeds this (default: 10, None to disable)

        Returns:
            List of task IDs that are stuck
        """
        stuck_task_ids = []
        timeout_threshold = datetime.utcnow() - timedelta(minutes=timeout_minutes)

        # Get all task keys from Redis
        task_keys = await self.redis.keys(f"{self.TASK_PREFIX}*")

        for task_key in task_keys:
            # Get task data
            task_data = await self.redis.hgetall(task_key)

            if not task_data:
                continue

            # Decode task data
            decoded_data = {}
            for key, value in task_data.items():
                key_str = key.decode() if isinstance(key, bytes) else key
                value_str = value.decode() if isinstance(value, bytes) else value
                decoded_data[key_str] = value_str

            # Only check tasks in PROCESSING status
            if decoded_data.get("status") != TaskStatus.PROCESSING.value:
                continue

            # Skip tasks without task_started_at (legacy tasks)
            if "task_started_at" not in decoded_data:
                continue

            # Parse task_started_at timestamp
            try:
                task_started_at = datetime.fromisoformat(decoded_data["task_started_at"])
            except (ValueError, KeyError):
                # Skip if timestamp is invalid
                logger.warning(f"Invalid task_started_at timestamp for task {decoded_data.get('task_id')}")
                continue

            # Check if task exceeded timeout
            if task_started_at < timeout_threshold:
                task_id = decoded_data.get("task_id")
                if task_id:
                    stuck_task_ids.append(task_id)
                    logger.warning(
                        f"Found stuck task {task_id}: started at {task_started_at}, "
                        f"exceeded {timeout_minutes} minute timeout"
                    )

        stuck_count = len(stuck_task_ids)
        logger.info(f"Found {stuck_count} stuck tasks with {timeout_minutes} minute timeout")

        # Alert if stuck count exceeds threshold
        if alert_threshold is not None and stuck_count > alert_threshold:
            logger.warning(
                f"ALERT: High stuck task count detected! "
                f"Found {stuck_count} stuck tasks (threshold: {alert_threshold}). "
                f"This may indicate a system issue. "
                f"Consider investigating worker health, Redis connectivity, or task complexity."
            )

        return stuck_task_ids

    async def move_to_dead_letter_queue(self, task_id: str, reason: str) -> bool:
        """
        Move a task to the dead letter queue for permanently failed tasks

        Args:
            task_id: Task identifier
            reason: Reason for moving to DLQ

        Returns:
            True if task was moved successfully
        """
        task_key = f"{self.TASK_PREFIX}{task_id}"

        # Check if task exists
        exists = await self.redis.exists(task_key)
        if not exists:
            logger.warning(f"Cannot move non-existent task {task_id} to DLQ")
            return False

        # Add task to dead letter queue
        await self.redis.lpush(self.DEAD_LETTER_QUEUE, task_id)

        # Mark task as being in DLQ and store reason
        await self.redis.hset(
            task_key,
            mapping={
                "in_dead_letter_queue": "true",
                "dead_letter_reason": reason,
                "moved_to_dlq_at": datetime.utcnow().isoformat(),
            }
        )

        logger.warning(f"Moved task {task_id} to dead letter queue: {reason}")
        return True

    async def get_dead_letter_queue_tasks(self, limit: int = 100) -> List[str]:
        """
        Get list of task IDs in the dead letter queue

        Args:
            limit: Maximum number of tasks to return (default: 100)

        Returns:
            List of task IDs in DLQ
        """
        task_ids_bytes = await self.redis.lrange(self.DEAD_LETTER_QUEUE, 0, limit - 1)

        task_ids = []
        for task_id_bytes in task_ids_bytes:
            task_id = task_id_bytes.decode() if isinstance(task_id_bytes, bytes) else task_id_bytes
            task_ids.append(task_id)

        logger.info(f"Retrieved {len(task_ids)} tasks from dead letter queue")
        return task_ids

    async def get_dead_letter_queue_count(self) -> int:
        """
        Get count of tasks in the dead letter queue

        Returns:
            Number of tasks in DLQ
        """
        count = await self.redis.llen(self.DEAD_LETTER_QUEUE)
        return count

    async def remove_from_dead_letter_queue(self, task_id: str) -> bool:
        """
        Remove a task from the dead letter queue

        Args:
            task_id: Task identifier

        Returns:
            True if task was removed
        """
        # Remove from DLQ list
        removed = await self.redis.lrem(self.DEAD_LETTER_QUEUE, 0, task_id)

        if removed > 0:
            # Update task data to remove DLQ flag
            task_key = f"{self.TASK_PREFIX}{task_id}"
            await self.redis.hdel(
                task_key,
                "in_dead_letter_queue",
                "dead_letter_reason",
                "moved_to_dlq_at"
            )
            logger.info(f"Removed task {task_id} from dead letter queue")
            return True

        logger.warning(f"Task {task_id} not found in dead letter queue")
        return False

    async def find_old_completed_tasks(self, cutoff_date: datetime) -> List[str]:
        """
        Find completed tasks that were finished before the cutoff date

        Args:
            cutoff_date: Tasks completed before this date will be returned

        Returns:
            List of task IDs for old completed tasks
        """
        old_task_ids = []

        # Get all task keys from Redis
        task_keys = await self.redis.keys(f"{self.TASK_PREFIX}*")

        for task_key in task_keys:
            # Get task data
            task_data = await self.redis.hgetall(task_key)

            if not task_data:
                continue

            # Decode task data
            decoded_data = {}
            for key, value in task_data.items():
                key_str = key.decode() if isinstance(key, bytes) else key
                value_str = value.decode() if isinstance(value, bytes) else value
                decoded_data[key_str] = value_str

            # Only check tasks with COMPLETED status
            if decoded_data.get("status") != TaskStatus.COMPLETED.value:
                continue

            # Skip tasks without completed_at timestamp
            if "completed_at" not in decoded_data:
                continue

            # Parse completed_at timestamp
            try:
                completed_at = datetime.fromisoformat(decoded_data["completed_at"])
            except (ValueError, KeyError):
                # Skip if timestamp is invalid
                logger.warning(f"Invalid completed_at timestamp for task {decoded_data.get('task_id')}")
                continue

            # Check if task was completed before cutoff date
            if completed_at < cutoff_date:
                task_id = decoded_data.get("task_id")
                if task_id:
                    old_task_ids.append(task_id)

        logger.info(f"Found {len(old_task_ids)} completed tasks older than {cutoff_date}")
        return old_task_ids

    async def delete_task(self, task_id: str) -> bool:
        """
        Delete a task and its result from Redis

        Args:
            task_id: Task identifier

        Returns:
            True if task was deleted, False if task didn't exist
        """
        task_key = f"{self.TASK_PREFIX}{task_id}"
        result_key = f"{self.RESULT_PREFIX}{task_id}"
        progress_history_key = f"{self.TASK_PREFIX}{task_id}:progress_history"

        # Check if task exists
        task_exists = await self.redis.exists(task_key)

        if not task_exists:
            logger.warning(f"Cannot delete non-existent task {task_id}")
            return False

        # Delete task, result, and progress history (Task 5.8)
        await self.redis.delete(task_key, result_key, progress_history_key)

        logger.info(f"Deleted task {task_id} and its progress history from Redis")
        return True

    async def cleanup_old_completed_tasks(
        self,
        cutoff_date: datetime,
        dry_run: bool = False
    ) -> int:
        """
        Clean up completed tasks older than cutoff date

        Args:
            cutoff_date: Tasks completed before this date will be deleted
            dry_run: If True, only report what would be deleted without deleting

        Returns:
            Number of tasks deleted (or that would be deleted in dry run)
        """
        old_task_ids = await self.find_old_completed_tasks(cutoff_date)

        if dry_run:
            logger.info(f"DRY RUN: Would delete {len(old_task_ids)} old completed tasks")
            return len(old_task_ids)

        deleted_count = 0
        for task_id in old_task_ids:
            if await self.delete_task(task_id):
                deleted_count += 1

        logger.info(f"Cleaned up {deleted_count} old completed tasks")
        return deleted_count

    async def record_task_completion(
        self,
        task_id: str,
        success: bool,
        duration_seconds: Optional[float] = None
    ) -> bool:
        """
        Record task completion metrics

        Args:
            task_id: Task identifier
            success: True if completed successfully, False if failed
            duration_seconds: Task duration in seconds (optional)

        Returns:
            True if metrics recorded successfully
        """
        try:
            # Increment total tasks counter
            await self.redis.incr("metrics:tasks:total")

            # Increment success or failure counter
            if success:
                await self.redis.incr("metrics:tasks:completed")
            else:
                await self.redis.incr("metrics:tasks:failed")

            # Record duration if provided
            if duration_seconds is not None:
                # Add to total duration for average calculation
                await self.redis.incrbyfloat("metrics:tasks:total_duration", duration_seconds)

            # Get retry count for this task
            task_key = f"{self.TASK_PREFIX}{task_id}"
            retry_count = await self.redis.hget(task_key, "retry_count")
            if retry_count:
                retry_count = int(retry_count.decode() if isinstance(retry_count, bytes) else retry_count)
                # Track retry distribution
                await self.redis.incr(f"metrics:tasks:retry_{retry_count}")

            logger.debug(f"Recorded metrics for task {task_id}: success={success}")
            return True

        except Exception as e:
            logger.error(f"Failed to record metrics for task {task_id}: {e}")
            return False

    async def get_task_metrics(self, task_id: str) -> Optional[Dict]:
        """
        Get metrics for a specific task

        Args:
            task_id: Task identifier

        Returns:
            Dictionary with task metrics or None if not found
        """
        task_key = f"{self.TASK_PREFIX}{task_id}"
        task_data = await self.redis.hgetall(task_key)

        if not task_data:
            return None

        # Decode task data
        decoded_data = {}
        for key, value in task_data.items():
            key_str = key.decode() if isinstance(key, bytes) else key
            value_str = value.decode() if isinstance(value, bytes) else value
            decoded_data[key_str] = value_str

        metrics = {
            "task_id": task_id,
            "status": decoded_data.get("status"),
            "retry_count": int(decoded_data.get("retry_count", 0))
        }

        # Calculate duration if task has started
        if "task_started_at" in decoded_data:
            try:
                started_at = datetime.fromisoformat(decoded_data["task_started_at"])

                if decoded_data.get("status") == TaskStatus.COMPLETED.value and "completed_at" in decoded_data:
                    completed_at = datetime.fromisoformat(decoded_data["completed_at"])
                    duration = (completed_at - started_at).total_seconds()
                    metrics["duration_seconds"] = duration
                    metrics["processing_time"] = duration
                else:
                    # Task still processing, calculate current duration
                    current_duration = (datetime.utcnow() - started_at).total_seconds()
                    metrics["current_duration_seconds"] = current_duration

            except (ValueError, KeyError):
                pass

        return metrics

    async def get_aggregate_metrics(self, time_window: Optional[str] = None) -> Dict:
        """
        Get aggregate metrics for all tasks

        Args:
            time_window: Time window for metrics (1h, 24h, 7d) - currently not implemented

        Returns:
            Dictionary with aggregate metrics
        """
        try:
            # Get counters
            total_tasks = await self.redis.get("metrics:tasks:total")
            completed_tasks = await self.redis.get("metrics:tasks:completed")
            failed_tasks = await self.redis.get("metrics:tasks:failed")
            total_duration = await self.redis.get("metrics:tasks:total_duration")

            # Decode bytes to integers
            total_tasks = int(total_tasks.decode() if total_tasks else 0)
            completed_tasks = int(completed_tasks.decode() if completed_tasks else 0)
            failed_tasks = int(failed_tasks.decode() if failed_tasks else 0)
            total_duration = float(total_duration.decode() if total_duration else 0)

            metrics = {
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "failed_tasks": failed_tasks
            }

            # Calculate success rate
            if total_tasks > 0:
                metrics["success_rate"] = (completed_tasks / total_tasks) * 100
            else:
                metrics["success_rate"] = 0

            # Calculate retry rate
            retried_tasks = 0
            for i in range(1, 4):  # Count tasks with 1-3 retries
                retry_count = await self.redis.get(f"metrics:tasks:retry_{i}")
                if retry_count:
                    retried_tasks += int(retry_count.decode() if isinstance(retry_count, bytes) else retry_count)

            if total_tasks > 0:
                metrics["retry_rate"] = (retried_tasks / total_tasks) * 100
                metrics["tasks_retried"] = retried_tasks
            else:
                metrics["retry_rate"] = 0
                metrics["tasks_retried"] = 0

            # Calculate average duration
            if completed_tasks > 0:
                metrics["average_duration_seconds"] = total_duration / completed_tasks
            else:
                metrics["average_duration_seconds"] = 0

            # Get DLQ count
            dlq_count = await self.get_dead_letter_queue_count()
            metrics["dead_letter_queue_count"] = dlq_count

            # Get retry distribution
            retry_distribution = {}
            for i in range(0, 4):
                retry_count = await self.redis.get(f"metrics:tasks:retry_{i}")
                if retry_count:
                    retry_distribution[f"retry_{i}"] = int(
                        retry_count.decode() if isinstance(retry_count, bytes) else retry_count
                    )
            metrics["retry_distribution"] = retry_distribution

            logger.debug(f"Retrieved aggregate metrics: {metrics}")
            return metrics

        except Exception as e:
            logger.error(f"Failed to get aggregate metrics: {e}")
            return {
                "total_tasks": 0,
                "completed_tasks": 0,
                "failed_tasks": 0,
                "success_rate": 0,
                "retry_rate": 0,
                "average_duration_seconds": 0,
                "dead_letter_queue_count": 0
            }

    async def reset_metrics(self) -> bool:
        """
        Reset all metrics counters

        Returns:
            True if reset successfully
        """
        try:
            # Delete all metrics keys
            metrics_keys = await self.redis.keys("metrics:*")
            if metrics_keys:
                await self.redis.delete(*metrics_keys)

            logger.info("Reset all metrics counters")
            return True

        except Exception as e:
            logger.error(f"Failed to reset metrics: {e}")
            return False

    async def record_progress_update(
        self,
        task_id: str,
        progress: int,
        operation: Optional[str],
        status: str
    ) -> bool:
        """
        Record progress update in history for debugging/monitoring (Task 5.8)

        Stores the last 10 progress updates for each task in Redis

        Args:
            task_id: Task identifier
            progress: Progress percentage (0-100)
            operation: Current operation description
            status: Task status (queued, processing, completed, failed)

        Returns:
            True if recorded successfully
        """
        try:
            history_key = f"{self.TASK_PREFIX}{task_id}:progress_history"

            # Create history entry
            history_entry = {
                "timestamp": datetime.utcnow().isoformat() + 'Z',
                "progress": progress,
                "operation": operation or "",
                "status": status
            }

            # Serialize to JSON
            import json
            entry_json = json.dumps(history_entry)

            # Add to history list (LPUSH adds to head of list - newest first)
            await self.redis.lpush(history_key, entry_json)

            # Trim to keep only last 10 entries (0-9 index)
            await self.redis.ltrim(history_key, 0, 9)

            logger.debug(f"Recorded progress update for task {task_id}: {progress}% - {operation}")
            return True

        except Exception as e:
            logger.warning(f"Failed to record progress history for task {task_id}: {e}")
            return False

    async def get_progress_history(
        self,
        task_id: str,
        limit: int = 10
    ) -> list:
        """
        Get progress history for a task (Task 5.8)

        Args:
            task_id: Task identifier
            limit: Maximum number of history entries to return (default: 10)

        Returns:
            List of progress updates (newest first), empty list if no history
        """
        try:
            history_key = f"{self.TASK_PREFIX}{task_id}:progress_history"

            # Get history entries (0 to limit-1)
            history_entries = await self.redis.lrange(history_key, 0, limit - 1)

            if not history_entries:
                return []

            # Parse JSON entries
            import json
            history = []
            for entry_bytes in history_entries:
                entry_json = entry_bytes.decode('utf-8')
                entry = json.loads(entry_json)
                history.append(entry)

            logger.debug(f"Retrieved {len(history)} progress history entries for task {task_id}")
            return history

        except Exception as e:
            logger.warning(f"Failed to get progress history for task {task_id}: {e}")
            return []


# Global Redis queue manager instance
redis_queue_manager: Optional[RedisQueueManager] = None


def get_redis_queue_manager() -> RedisQueueManager:
    """Get global Redis queue manager instance"""
    if redis_queue_manager is None:
        raise RuntimeError("Redis queue manager not initialized")
    return redis_queue_manager


async def init_redis_queue_manager(redis_url: str):
    """Initialize global Redis queue manager"""
    global redis_queue_manager
    redis_queue_manager = RedisQueueManager(redis_url)
    await redis_queue_manager.connect()
    return redis_queue_manager
