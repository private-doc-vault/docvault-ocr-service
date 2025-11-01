"""
OCR Worker Process
Processes OCR tasks from Redis queue
"""
import asyncio
import signal
import sys
import os
import logging
import io
import time
from typing import Optional
from datetime import datetime

from .redis_queue import init_redis_queue_manager, get_redis_queue_manager
from .document_processor import DocumentProcessor
from .ocr_service import OCRService
from .models import OCRResult as OCRResultModel, TaskStatus
from .webhook_client import WebhookClient, WebhookDeliveryError

# Import metadata and categorization services
try:
    from .metadata_extractor_v2 import MetadataExtractorV2
    METADATA_AVAILABLE = True
except ImportError:
    METADATA_AVAILABLE = False
    logging.warning("MetadataExtractorV2 not available")

try:
    from .document_categorizer_v2 import DocumentCategorizerV2
    CATEGORIZER_AVAILABLE = True
except ImportError:
    CATEGORIZER_AVAILABLE = False
    logging.warning("DocumentCategorizerV2 not available")


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OCRWorker:
    """
    Worker process for OCR task processing

    Features:
    - Dequeues tasks from Redis (priority: high -> normal -> low)
    - Processes documents through OCR pipeline
    - Updates task status and progress
    - Handles errors with retry logic
    - Graceful shutdown support
    """

    def __init__(
        self,
        redis_url: str,
        poll_interval: float = 1.0,
        max_retries: int = 3
    ):
        """
        Initialize OCR worker

        Args:
            redis_url: Redis connection URL
            poll_interval: Seconds to wait between queue checks
            max_retries: Maximum retry attempts for failed tasks
        """
        self.redis_url = redis_url
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.running = False
        self.shutdown_requested = False

        # Initialize services
        self.document_processor = DocumentProcessor()
        self.ocr_service = OCRService()

        # Initialize metadata and categorization if available
        self.metadata_extractor = MetadataExtractorV2() if METADATA_AVAILABLE else None
        self.document_categorizer = DocumentCategorizerV2() if CATEGORIZER_AVAILABLE else None

        # Initialize webhook client if configured
        try:
            self.webhook_client = WebhookClient.from_env()
            logger.info("Webhook client initialized")
        except ValueError as e:
            logger.warning(f"Webhook client not configured: {e}")
            self.webhook_client = None

        logger.info("OCR Worker initialized")

    async def start(self):
        """Start the worker process"""
        logger.info("Starting OCR Worker...")

        # Initialize Redis connection
        try:
            await init_redis_queue_manager(self.redis_url)
            logger.info("Connected to Redis queue")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self.running = True
        logger.info("OCR Worker started successfully")

        # Start main processing loop
        await self._process_loop()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True

    async def _process_loop(self):
        """Main processing loop"""
        logger.info("Entering main processing loop")

        while self.running and not self.shutdown_requested:
            try:
                # Check for tasks in queue (priority order: high -> normal -> low)
                redis_manager = get_redis_queue_manager()
                task_id = await redis_manager.dequeue_task()

                if task_id:
                    logger.info(f"Dequeued task: {task_id}")

                    # Process the task
                    try:
                        await self._process_task(task_id)
                    except Exception as e:
                        logger.error(f"Error processing task {task_id}: {e}", exc_info=True)
                        await self._handle_task_error(task_id, str(e))
                else:
                    # No tasks available, wait before checking again
                    await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)

        logger.info("Exiting processing loop")
        await self._shutdown()

    async def _process_task(self, task_id: str):
        """
        Process a single OCR task

        Args:
            task_id: Task identifier
        """
        start_time = time.time()
        redis_manager = get_redis_queue_manager()

        try:
            # Update status to PROCESSING
            await redis_manager.update_task_status(
                task_id,
                TaskStatus.PROCESSING,
                progress=0,
                message="Starting OCR processing"
            )

            # Get task details
            task_status = await redis_manager.get_task_status(task_id)
            if not task_status:
                raise Exception("Task not found")

            # Get file path from task
            file_path = await redis_manager.get_task_file_path(task_id)
            if not file_path:
                raise Exception("File path not found in task metadata")

            logger.info(f"Processing file: {file_path}")

            # Check if file exists
            if not os.path.exists(file_path):
                raise Exception(f"File not found: {file_path}")

            # Get language from task
            language = task_status.message if hasattr(task_status, 'language') else "pol"
            # Try to get language from Redis directly
            task_key = f"task:{task_id}"
            task_data = await redis_manager.redis.hgetall(task_key)
            if task_data and b"language" in task_data:
                language = task_data[b"language"].decode()

            # Step 1: Convert document to images (25% progress)
            await redis_manager.update_task_status(
                task_id,
                TaskStatus.PROCESSING,
                progress=10,
                message="Converting document to images"
            )

            with open(file_path, 'rb') as f:
                processed_doc = self.document_processor.process(f)

            logger.info(f"Document processed: {processed_doc.page_count} pages")

            # Step 2: Extract text - use native PDF text if available, otherwise OCR (25% - 75% progress)
            # Check if we have native text from PDF
            use_native_text = processed_doc.has_native_text and processed_doc.native_text

            if use_native_text:
                logger.info(f"Using native PDF text extraction (faster and more accurate)")
                await redis_manager.update_task_status(
                    task_id,
                    TaskStatus.PROCESSING,
                    progress=25,
                    message=f"Using native text from PDF ({processed_doc.page_count} pages)"
                )

                # Send progress webhook at 25% milestone
                await self._send_progress_webhook(
                    task_id=task_id,
                    progress=25,
                    current_operation=f"Using native text from PDF ({processed_doc.page_count} pages)"
                )

                all_text = []
                page_results = []

                for idx, page_text in enumerate(processed_doc.native_text):
                    page_num = idx + 1
                    all_text.append(page_text)
                    page_results.append({
                        "page": page_num,
                        "text": page_text,
                        "confidence": 95.0,  # Native text is high quality
                        "source": "native_pdf"
                    })

                    # Update progress (25% to 75%)
                    progress = 25 + int((page_num / processed_doc.page_count) * 50)
                    await redis_manager.update_task_status(
                        task_id,
                        TaskStatus.PROCESSING,
                        progress=progress,
                        message=f"Processed page {page_num}/{processed_doc.page_count}"
                    )

                full_text = "\n\n".join(all_text)
                avg_confidence = 95.0
                logger.info(f"Native text extraction completed with high confidence: {avg_confidence:.2f}%")

            else:
                # Perform OCR on each page
                logger.info(f"Performing OCR on {processed_doc.page_count} pages")
                await redis_manager.update_task_status(
                    task_id,
                    TaskStatus.PROCESSING,
                    progress=25,
                    message=f"Performing OCR on {processed_doc.page_count} pages"
                )

                # Send progress webhook at 25% milestone (Task 5.7)
                await self._send_progress_webhook(
                    task_id=task_id,
                    progress=25,
                    current_operation=f"Performing OCR on {processed_doc.page_count} pages"
                )

                all_text = []
                page_results = []
                total_confidence = 0.0

                for idx, image in enumerate(processed_doc.images):
                    page_num = idx + 1
                    logger.info(f"Processing page {page_num}/{processed_doc.page_count}")

                    # Convert PIL Image to bytes for OCR service
                    img_byte_arr = io.BytesIO()
                    image.save(img_byte_arr, format='PNG')
                    img_byte_arr.seek(0)

                    # Perform OCR with enhanced preprocessing
                    # Use "auto" enhancement level for adaptive processing
                    ocr_result = self.ocr_service.extract_text(
                        img_byte_arr,
                        language=language,
                        dpi=processed_doc.dpi or 300,
                        preprocess=True,  # Enable enhanced preprocessing
                        enhance_level="auto"  # Auto-detect optimal enhancement based on image quality
                    )

                    all_text.append(ocr_result.text)
                    total_confidence += ocr_result.confidence
                    page_results.append({
                        "page": page_num,
                        "text": ocr_result.text,
                        "confidence": ocr_result.confidence,
                        "source": "ocr"
                    })

                    # Update progress (25% to 75% based on page completion)
                    progress = 25 + int((page_num / processed_doc.page_count) * 50)
                    await redis_manager.update_task_status(
                        task_id,
                        TaskStatus.PROCESSING,
                        progress=progress,
                        message=f"Processed page {page_num}/{processed_doc.page_count}"
                    )

                    # Send progress webhook at 50% milestone (Task 5.7)
                    if progress >= 48 and progress <= 52:
                        await self._send_progress_webhook(
                            task_id=task_id,
                            progress=progress,
                            current_operation=f"Performing OCR on page {page_num}/{processed_doc.page_count}"
                        )

                # Combine all text
                full_text = "\n\n".join(all_text)
                avg_confidence = total_confidence / len(processed_doc.images) if processed_doc.images else 0.0

                logger.info(f"OCR completed with average confidence: {avg_confidence:.2f}%")

            # Step 3: Extract metadata (75% - 85% progress)
            metadata = {}
            if self.metadata_extractor:
                try:
                    await redis_manager.update_task_status(
                        task_id,
                        TaskStatus.PROCESSING,
                        progress=75,
                        message="Extracting metadata"
                    )

                    # Send progress webhook at 75% milestone (Task 5.7)
                    await self._send_progress_webhook(
                        task_id=task_id,
                        progress=75,
                        current_operation="Extracting metadata"
                    )

                    metadata = self.metadata_extractor.extract(full_text)
                    logger.info(f"Extracted metadata: {list(metadata.keys())}")
                except Exception as e:
                    logger.warning(f"Metadata extraction failed: {e}")

            # Step 4: Categorize document (85% - 95% progress)
            category = None
            if self.document_categorizer:
                try:
                    await redis_manager.update_task_status(
                        task_id,
                        TaskStatus.PROCESSING,
                        progress=85,
                        message="Categorizing document"
                    )
                    category = self.document_categorizer.categorize(full_text, metadata)
                    logger.info(f"Document categorized as: {category}")
                except Exception as e:
                    logger.warning(f"Document categorization failed: {e}")

            # Add category to metadata if available
            if category:
                metadata["category"] = category

            # Step 5: Store result (95% - 100% progress)
            await redis_manager.update_task_status(
                task_id,
                TaskStatus.PROCESSING,
                progress=95,
                message="Storing results"
            )

            processing_time = time.time() - start_time

            # Create result object
            result = OCRResultModel(
                task_id=task_id,
                text=full_text,
                confidence=avg_confidence,
                language=language,
                page_count=processed_doc.page_count,
                processing_time=processing_time,
                pages=page_results,
                metadata=metadata
            )

            # Store result in Redis
            await redis_manager.store_result(task_id, result)

            logger.info(f"Task {task_id} completed successfully in {processing_time:.2f}s")

            # Send webhook notification to backend
            await self._send_completion_webhook(task_id, result)

            # NOTE: Files are NOT cleaned up here as they are managed by backend
            # Files remain in shared storage and are cleaned up by backend's OrphanedFileCleanupService
            # based on configured retention policy

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            # Send failure webhook to backend
            await self._send_failure_webhook(task_id, str(e))
            raise

    async def _send_completion_webhook(self, task_id: str, result: OCRResultModel):
        """
        Send webhook notification for successful task completion

        Args:
            task_id: Task identifier
            result: OCR processing result
        """
        if not self.webhook_client:
            logger.debug("Webhook client not configured, skipping webhook notification")
            return

        try:
            # Get document_id from Redis
            redis_manager = get_redis_queue_manager()
            task_key = f"task:{task_id}"
            task_data = await redis_manager.redis.hgetall(task_key)

            document_id = None
            if task_data and b"document_id" in task_data:
                document_id = task_data[b"document_id"].decode()

            if not document_id:
                logger.warning(f"No document_id found for task {task_id}, skipping webhook")
                return

            # Prepare webhook payload
            webhook_result = {
                "text": result.text,
                "confidence": result.confidence,
                "language": result.language,
                "page_count": result.page_count,
                "processing_time": result.processing_time,
                "metadata": result.metadata or {}
            }

            # Send webhook
            await self.webhook_client.send_webhook(
                task_id=task_id,
                document_id=document_id,
                status="completed",
                result=webhook_result
            )

            logger.info(f"Webhook sent successfully for task {task_id}, document {document_id}")

        except WebhookDeliveryError as e:
            # Log webhook failure but don't fail the task
            logger.error(f"Failed to deliver webhook for task {task_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending webhook for task {task_id}: {e}", exc_info=True)

    async def _send_failure_webhook(self, task_id: str, error_message: str):
        """
        Send webhook notification for task failure

        Args:
            task_id: Task identifier
            error_message: Error message
        """
        if not self.webhook_client:
            logger.debug("Webhook client not configured, skipping webhook notification")
            return

        try:
            # Get document_id from Redis
            redis_manager = get_redis_queue_manager()
            task_key = f"task:{task_id}"
            task_data = await redis_manager.redis.hgetall(task_key)

            document_id = None
            if task_data and b"document_id" in task_data:
                document_id = task_data[b"document_id"].decode()

            if not document_id:
                logger.warning(f"No document_id found for task {task_id}, skipping webhook")
                return

            # Send webhook
            await self.webhook_client.send_webhook(
                task_id=task_id,
                document_id=document_id,
                status="failed",
                error=error_message
            )

            logger.info(f"Failure webhook sent for task {task_id}, document {document_id}")

        except WebhookDeliveryError as e:
            # Log webhook failure but don't fail the task further
            logger.error(f"Failed to deliver failure webhook for task {task_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error sending failure webhook for task {task_id}: {e}", exc_info=True)

    async def _send_progress_webhook(self, task_id: str, progress: int, current_operation: str):
        """
        Send progress webhook notification to backend (Task 5.7)
        Also records progress update in Redis history (Task 5.8)

        Args:
            task_id: Task identifier
            progress: Progress percentage (0-100)
            current_operation: Description of current operation
        """
        if not self.webhook_client:
            logger.debug("Webhook client not configured, skipping progress webhook")
            return

        try:
            # Get document_id from Redis
            redis_manager = get_redis_queue_manager()
            task_key = f"task:{task_id}"
            task_data = await redis_manager.redis.hgetall(task_key)

            document_id = None
            if task_data and b"document_id" in task_data:
                document_id = task_data[b"document_id"].decode()

            if not document_id:
                logger.debug(f"No document_id found for task {task_id}, skipping progress webhook")
                return

            # Record progress in history (Task 5.8)
            await redis_manager.record_progress_update(
                task_id=task_id,
                progress=progress,
                operation=current_operation,
                status="processing"
            )

            # Send progress webhook
            await self.webhook_client.send_webhook(
                task_id=task_id,
                document_id=document_id,
                status="processing",
                progress=progress,
                current_operation=current_operation
            )

            logger.debug(
                f"Progress webhook sent for task {task_id}: {progress}% - {current_operation}"
            )

        except WebhookDeliveryError as e:
            # Log webhook failure but don't fail the task
            logger.warning(f"Failed to deliver progress webhook for task {task_id}: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error sending progress webhook for task {task_id}: {e}")

    async def _handle_task_error(self, task_id: str, error_message: str):
        """
        Handle task processing error

        Args:
            task_id: Task identifier
            error_message: Error message
        """
        redis_manager = get_redis_queue_manager()

        try:
            # Get current retry count
            task_key = f"task:{task_id}"
            task_data = await redis_manager.redis.hgetall(task_key)

            if task_data and b"retry_count" in task_data:
                retry_count = int(task_data[b"retry_count"].decode())
            else:
                retry_count = 0

            # Check if we should retry
            if retry_count < self.max_retries:
                # Retry the task
                logger.info(f"Retrying task {task_id} (attempt {retry_count + 1}/{self.max_retries})")
                success = await redis_manager.retry_task(task_id, max_retries=self.max_retries)

                if success:
                    logger.info(f"Task {task_id} requeued for retry")
                else:
                    # Max retries exceeded
                    await redis_manager.update_task_status(
                        task_id,
                        TaskStatus.FAILED,
                        progress=0,
                        message=f"Failed after {self.max_retries} retries: {error_message}"
                    )
                    logger.error(f"Task {task_id} failed after {self.max_retries} retries")
            else:
                # Mark as failed
                await redis_manager.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    progress=0,
                    message=f"Processing failed: {error_message}"
                )
                logger.error(f"Task {task_id} marked as FAILED")

        except Exception as e:
            logger.error(f"Error handling task error for {task_id}: {e}", exc_info=True)

    async def _shutdown(self):
        """Gracefully shut down the worker"""
        logger.info("Shutting down OCR Worker...")

        self.running = False

        # Disconnect from Redis
        try:
            redis_manager = get_redis_queue_manager()
            await redis_manager.disconnect()
            logger.info("Disconnected from Redis")
        except Exception as e:
            logger.error(f"Error disconnecting from Redis: {e}")

        logger.info("OCR Worker shutdown complete")


async def main():
    """Main entry point for worker process"""
    # Get Redis URL from environment
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Get worker configuration from environment
    poll_interval = float(os.getenv("WORKER_POLL_INTERVAL", "1.0"))
    max_retries = int(os.getenv("WORKER_MAX_RETRIES", "3"))

    logger.info(f"Starting OCR Worker with Redis: {redis_url}")
    logger.info(f"Configuration: poll_interval={poll_interval}s, max_retries={max_retries}")

    # Create and start worker
    worker = OCRWorker(
        redis_url=redis_url,
        poll_interval=poll_interval,
        max_retries=max_retries
    )

    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Worker error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
