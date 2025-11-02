"""
Tests for OCR Worker Progress Webhook Functionality (Task 5.7)
Tests that worker sends progress webhooks at key milestones during processing
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import io
from PIL import Image

from app.worker import OCRWorker
from app.models import TaskStatus, OCRResult


class TestWorkerProgressWebhooks:
    """Test that worker sends progress webhooks at key milestones"""

    @pytest.fixture
    def mock_redis_manager(self):
        """Create mock Redis queue manager"""
        manager = AsyncMock()
        manager.update_task_status = AsyncMock()
        manager.get_task_status = AsyncMock()
        manager.get_task_file_path = AsyncMock(return_value="/shared/test.pdf")
        manager.store_result = AsyncMock()
        manager.redis = AsyncMock()
        manager.redis.hgetall = AsyncMock(return_value={
            b"language": b"eng",
            b"document_id": b"doc-123"
        })
        return manager

    @pytest.fixture
    def mock_webhook_client(self):
        """Create mock webhook client"""
        client = AsyncMock()
        client.send_webhook = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def mock_document_processor(self):
        """Create mock document processor"""
        processor = Mock()
        # Create a simple mock document with 4 pages
        mock_doc = Mock()
        mock_doc.page_count = 4
        mock_doc.dpi = 300

        # Create 4 simple test images
        images = []
        for _ in range(4):
            img = Image.new('RGB', (100, 100), color='white')
            images.append(img)
        mock_doc.images = images

        # Add native_text for PDFs (empty means OCR will be used)
        mock_doc.native_text = []

        processor.process = Mock(return_value=mock_doc)
        return processor

    @pytest.fixture
    def mock_ocr_service(self):
        """Create mock OCR service"""
        service = Mock()
        mock_result = Mock()
        mock_result.text = "Sample OCR text"
        mock_result.confidence = 95.0
        service.extract_text = Mock(return_value=mock_result)
        return service

    @pytest.mark.asyncio
    async def test_worker_sends_progress_webhook_at_25_percent(
        self,
        mock_redis_manager,
        mock_webhook_client,
        mock_document_processor,
        mock_ocr_service
    ):
        """Test worker sends progress webhook at 25% (after document conversion)"""
        with patch('app.worker.get_redis_queue_manager', return_value=mock_redis_manager):
            with patch('app.worker.WebhookClient') as mock_webhook_class:
                mock_webhook_class.from_env.return_value = mock_webhook_client

                worker = OCRWorker(redis_url="redis://localhost", poll_interval=1.0)
                worker.document_processor = mock_document_processor
                worker.ocr_service = mock_ocr_service
                worker.webhook_client = mock_webhook_client
                worker.metadata_extractor = None
                worker.document_categorizer = None

                # Mock file system
                with patch('os.path.exists', return_value=True):
                    with patch('builtins.open', create=True):
                        await worker._process_task("task-123")

                # Verify progress webhook was sent at 25%
                progress_calls = [
                    call for call in mock_webhook_client.send_webhook.call_args_list
                    if call[1].get('progress') == 25 and call[1].get('status') == 'processing'
                ]

                assert len(progress_calls) >= 1, "Worker should send progress webhook at 25%"
                call_kwargs = progress_calls[0][1]
                assert call_kwargs['task_id'] == "task-123"
                assert call_kwargs['document_id'] == "doc-123"
                assert 'current_operation' in call_kwargs

    @pytest.mark.asyncio
    async def test_worker_sends_progress_webhook_at_50_percent(
        self,
        mock_redis_manager,
        mock_webhook_client,
        mock_document_processor,
        mock_ocr_service
    ):
        """Test worker sends progress webhook at 50% (mid-OCR processing)"""
        with patch('app.worker.get_redis_queue_manager', return_value=mock_redis_manager):
            with patch('app.worker.WebhookClient') as mock_webhook_class:
                mock_webhook_class.from_env.return_value = mock_webhook_client

                worker = OCRWorker(redis_url="redis://localhost", poll_interval=1.0)
                worker.document_processor = mock_document_processor
                worker.ocr_service = mock_ocr_service
                worker.webhook_client = mock_webhook_client
                worker.metadata_extractor = None
                worker.document_categorizer = None

                with patch('os.path.exists', return_value=True):
                    with patch('builtins.open', create=True):
                        await worker._process_task("task-123")

                # Check if any progress webhook was sent around 50%
                progress_calls = [
                    call for call in mock_webhook_client.send_webhook.call_args_list
                    if call[1].get('status') == 'processing' and
                       45 <= call[1].get('progress', 0) <= 55
                ]

                assert len(progress_calls) >= 1, "Worker should send progress webhook around 50%"

    @pytest.mark.asyncio
    async def test_worker_sends_progress_webhook_at_75_percent(
        self,
        mock_redis_manager,
        mock_webhook_client,
        mock_document_processor,
        mock_ocr_service
    ):
        """Test worker sends progress webhook at 75% (before metadata extraction)"""
        with patch('app.worker.get_redis_queue_manager', return_value=mock_redis_manager):
            with patch('app.worker.WebhookClient') as mock_webhook_class:
                mock_webhook_class.from_env.return_value=mock_webhook_client

                worker = OCRWorker(redis_url="redis://localhost", poll_interval=1.0)
                worker.document_processor = mock_document_processor
                worker.ocr_service = mock_ocr_service
                worker.webhook_client = mock_webhook_client
                worker.metadata_extractor = Mock()
                worker.metadata_extractor.extract = Mock(return_value={})
                worker.document_categorizer = None

                with patch('os.path.exists', return_value=True):
                    with patch('builtins.open', create=True):
                        await worker._process_task("task-123")

                # Check for progress webhook at 75%
                progress_calls = [
                    call for call in mock_webhook_client.send_webhook.call_args_list
                    if call[1].get('progress') == 75 and call[1].get('status') == 'processing'
                ]

                assert len(progress_calls) >= 1, "Worker should send progress webhook at 75%"

    @pytest.mark.asyncio
    async def test_worker_sends_completion_webhook_at_100_percent(
        self,
        mock_redis_manager,
        mock_webhook_client,
        mock_document_processor,
        mock_ocr_service
    ):
        """Test worker sends completion webhook at 100%"""
        with patch('app.worker.get_redis_queue_manager', return_value=mock_redis_manager):
            with patch('app.worker.WebhookClient') as mock_webhook_class:
                mock_webhook_class.from_env.return_value = mock_webhook_client

                worker = OCRWorker(redis_url="redis://localhost", poll_interval=1.0)
                worker.document_processor = mock_document_processor
                worker.ocr_service = mock_ocr_service
                worker.webhook_client = mock_webhook_client
                worker.metadata_extractor = None
                worker.document_categorizer = None

                with patch('os.path.exists', return_value=True):
                    with patch('builtins.open', create=True):
                        await worker._process_task("task-123")

                # Verify completion webhook was sent
                completion_calls = [
                    call for call in mock_webhook_client.send_webhook.call_args_list
                    if call[1].get('status') == 'completed'
                ]

                assert len(completion_calls) == 1, "Worker should send completion webhook"
                call_kwargs = completion_calls[0][1]
                assert call_kwargs['task_id'] == "task-123"
                assert call_kwargs['document_id'] == "doc-123"
                assert 'result' in call_kwargs

    @pytest.mark.asyncio
    async def test_worker_sends_progress_webhooks_in_order(
        self,
        mock_redis_manager,
        mock_webhook_client,
        mock_document_processor,
        mock_ocr_service
    ):
        """Test worker sends progress webhooks in ascending order"""
        with patch('app.worker.get_redis_queue_manager', return_value=mock_redis_manager):
            with patch('app.worker.WebhookClient') as mock_webhook_class:
                mock_webhook_class.from_env.return_value = mock_webhook_client

                worker = OCRWorker(redis_url="redis://localhost", poll_interval=1.0)
                worker.document_processor = mock_document_processor
                worker.ocr_service = mock_ocr_service
                worker.webhook_client = mock_webhook_client
                worker.metadata_extractor = Mock()
                worker.metadata_extractor.extract = Mock(return_value={})
                worker.document_categorizer = None

                with patch('os.path.exists', return_value=True):
                    with patch('builtins.open', create=True):
                        await worker._process_task("task-123")

                # Extract all progress values from webhook calls
                progress_values = [
                    call[1].get('progress')
                    for call in mock_webhook_client.send_webhook.call_args_list
                    if call[1].get('status') == 'processing' and call[1].get('progress') is not None
                ]

                # Verify progress values are in ascending order
                assert progress_values == sorted(progress_values), \
                    "Progress webhooks should be sent in ascending order"

                # Verify we hit key milestones
                assert any(p == 25 for p in progress_values), "Should include 25% milestone"
                assert any(p == 75 for p in progress_values), "Should include 75% milestone"

    @pytest.mark.asyncio
    async def test_worker_includes_operation_message_in_progress_webhooks(
        self,
        mock_redis_manager,
        mock_webhook_client,
        mock_document_processor,
        mock_ocr_service
    ):
        """Test worker includes current_operation message in progress webhooks"""
        with patch('app.worker.get_redis_queue_manager', return_value=mock_redis_manager):
            with patch('app.worker.WebhookClient') as mock_webhook_class:
                mock_webhook_class.from_env.return_value = mock_webhook_client

                worker = OCRWorker(redis_url="redis://localhost", poll_interval=1.0)
                worker.document_processor = mock_document_processor
                worker.ocr_service = mock_ocr_service
                worker.webhook_client = mock_webhook_client
                worker.metadata_extractor = None
                worker.document_categorizer = None

                with patch('os.path.exists', return_value=True):
                    with patch('builtins.open', create=True):
                        await worker._process_task("task-123")

                # Check that all progress webhooks include current_operation
                progress_calls = [
                    call for call in mock_webhook_client.send_webhook.call_args_list
                    if call[1].get('status') == 'processing'
                ]

                for call in progress_calls:
                    assert 'current_operation' in call[1], \
                        "All progress webhooks should include current_operation"
                    assert call[1]['current_operation'] is not None, \
                        "current_operation should not be None"
                    assert len(call[1]['current_operation']) > 0, \
                        "current_operation should be descriptive"

    @pytest.mark.asyncio
    async def test_worker_gracefully_handles_webhook_failures(
        self,
        mock_redis_manager,
        mock_document_processor,
        mock_ocr_service
    ):
        """Test worker continues processing even if progress webhooks fail"""
        failing_webhook_client = AsyncMock()
        failing_webhook_client.send_webhook = AsyncMock(side_effect=Exception("Webhook failed"))

        with patch('app.worker.get_redis_queue_manager', return_value=mock_redis_manager):
            with patch('app.worker.WebhookClient') as mock_webhook_class:
                mock_webhook_class.from_env.return_value = failing_webhook_client

                worker = OCRWorker(redis_url="redis://localhost", poll_interval=1.0)
                worker.document_processor = mock_document_processor
                worker.ocr_service = mock_ocr_service
                worker.webhook_client = failing_webhook_client
                worker.metadata_extractor = None
                worker.document_categorizer = None

                # Should not raise exception despite webhook failures
                with patch('os.path.exists', return_value=True):
                    with patch('builtins.open', create=True):
                        await worker._process_task("task-123")

                # Verify result was still stored despite webhook failures
                mock_redis_manager.store_result.assert_called_once()
