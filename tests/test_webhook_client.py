"""
Tests for Webhook Client
Following TDD methodology - these tests define the expected behavior before implementation
"""
import pytest
import httpx
import respx
from unittest.mock import Mock, patch, AsyncMock
import hashlib
import hmac
import json
from datetime import datetime


# These imports will exist after implementation
# For now, they define the expected interface
from app.webhook_client import WebhookClient, WebhookDeliveryError, WebhookSignatureError


class TestWebhookClientInitialization:
    """Test webhook client initialization"""

    def test_client_initializes_with_required_params(self):
        """Test that client can be initialized with backend URL and secret"""
        client = WebhookClient(
            backend_url="http://backend:8000",
            webhook_secret="test-secret-key"
        )

        assert client.backend_url == "http://backend:8000"
        assert client.webhook_secret == "test-secret-key"
        assert client.max_retries == 3  # Default
        assert client.timeout == 30  # Default timeout in seconds

    def test_client_initializes_with_custom_retry_config(self):
        """Test client initialization with custom retry configuration"""
        client = WebhookClient(
            backend_url="http://backend:8000",
            webhook_secret="test-secret",
            max_retries=5,
            timeout=60
        )

        assert client.max_retries == 5
        assert client.timeout == 60

    def test_client_validates_backend_url(self):
        """Test that invalid backend URLs are rejected"""
        with pytest.raises(ValueError, match="Invalid backend URL"):
            WebhookClient(
                backend_url="not-a-url",
                webhook_secret="secret"
            )

    def test_client_requires_webhook_secret(self):
        """Test that webhook secret is required"""
        with pytest.raises(ValueError, match="Webhook secret is required"):
            WebhookClient(
                backend_url="http://backend:8000",
                webhook_secret=""
            )


class TestWebhookSignatureGeneration:
    """Test HMAC signature generation for webhook security"""

    def test_generates_valid_hmac_signature(self):
        """Test that client generates valid HMAC-SHA256 signatures"""
        client = WebhookClient(
            backend_url="http://backend:8000",
            webhook_secret="test-secret-key"
        )

        payload = {"task_id": "123", "status": "completed"}
        payload_json = json.dumps(payload, separators=(',', ':'))

        signature = client._generate_signature(payload_json)

        # Verify signature is a valid hex string
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 produces 64 hex characters

        # Verify signature matches expected HMAC
        expected = hmac.new(
            "test-secret-key".encode(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()

        assert signature == expected

    def test_signature_changes_with_different_payload(self):
        """Test that different payloads produce different signatures"""
        client = WebhookClient(
            backend_url="http://backend:8000",
            webhook_secret="test-secret-key"
        )

        payload1 = json.dumps({"task_id": "123"})
        payload2 = json.dumps({"task_id": "456"})

        sig1 = client._generate_signature(payload1)
        sig2 = client._generate_signature(payload2)

        assert sig1 != sig2

    def test_signature_changes_with_different_secret(self):
        """Test that different secrets produce different signatures"""
        payload = json.dumps({"task_id": "123"})

        client1 = WebhookClient("http://backend:8000", "secret1")
        client2 = WebhookClient("http://backend:8000", "secret2")

        sig1 = client1._generate_signature(payload)
        sig2 = client2._generate_signature(payload)

        assert sig1 != sig2


class TestWebhookPayloadConstruction:
    """Test webhook payload construction"""

    def test_builds_completed_webhook_payload(self):
        """Test construction of completed status webhook payload"""
        client = WebhookClient("http://backend:8000", "secret")

        payload = client._build_payload(
            task_id="task-123",
            document_id="doc-456",
            status="completed",
            result={
                "text": "Extracted text content",
                "confidence": 95.5,
                "language": "eng",
                "metadata": {
                    "dates": ["2024-01-15"],
                    "amounts": [1234.56]
                },
                "category": {
                    "primary_category": "Invoice"
                }
            }
        )

        assert payload["task_id"] == "task-123"
        assert payload["document_id"] == "doc-456"
        assert payload["status"] == "completed"
        assert payload["result"]["text"] == "Extracted text content"
        assert payload["result"]["confidence"] == 95.5
        assert payload["result"]["language"] == "eng"
        assert payload["result"]["metadata"]["dates"] == ["2024-01-15"]
        assert payload["result"]["category"]["primary_category"] == "Invoice"

    def test_builds_failed_webhook_payload(self):
        """Test construction of failed status webhook payload"""
        client = WebhookClient("http://backend:8000", "secret")

        payload = client._build_payload(
            task_id="task-123",
            document_id="doc-456",
            status="failed",
            error="OCR processing timeout"
        )

        assert payload["task_id"] == "task-123"
        assert payload["document_id"] == "doc-456"
        assert payload["status"] == "failed"
        assert payload["error"] == "OCR processing timeout"
        assert "result" not in payload

    def test_payload_includes_timestamp(self):
        """Test that payload includes timestamp"""
        client = WebhookClient("http://backend:8000", "secret")

        payload = client._build_payload(
            task_id="task-123",
            document_id="doc-456",
            status="completed",
            result={"text": "content"}
        )

        assert "timestamp" in payload
        # Verify timestamp is ISO format
        datetime.fromisoformat(payload["timestamp"].replace('Z', '+00:00'))

    def test_builds_progress_webhook_payload(self):
        """Test construction of progress update webhook payload (Task 5.2)"""
        client = WebhookClient("http://backend:8000", "secret")

        payload = client._build_payload(
            task_id="task-123",
            document_id="doc-456",
            status="processing",
            progress=45,
            current_operation="Performing OCR on page 5/10"
        )

        assert payload["task_id"] == "task-123"
        assert payload["document_id"] == "doc-456"
        assert payload["status"] == "processing"
        assert payload["progress"] == 45
        assert payload["current_operation"] == "Performing OCR on page 5/10"
        assert "result" not in payload
        assert "error" not in payload
        assert "timestamp" in payload

    def test_progress_payload_without_operation(self):
        """Test progress webhook with progress only (no operation message)"""
        client = WebhookClient("http://backend:8000", "secret")

        payload = client._build_payload(
            task_id="task-123",
            document_id="doc-456",
            status="processing",
            progress=75
        )

        assert payload["progress"] == 75
        assert "current_operation" not in payload

    def test_progress_payload_without_progress(self):
        """Test progress webhook with operation only (no progress percentage)"""
        client = WebhookClient("http://backend:8000", "secret")

        payload = client._build_payload(
            task_id="task-123",
            document_id="doc-456",
            status="processing",
            current_operation="Extracting metadata"
        )

        assert payload["current_operation"] == "Extracting metadata"
        assert "progress" not in payload

    def test_validates_progress_range(self):
        """Test that progress must be between 0 and 100"""
        client = WebhookClient("http://backend:8000", "secret")

        # Test invalid progress values
        with pytest.raises(ValueError, match="Progress must be between 0 and 100"):
            client._build_payload(
                task_id="task-123",
                document_id="doc-456",
                status="processing",
                progress=-1
            )

        with pytest.raises(ValueError, match="Progress must be between 0 and 100"):
            client._build_payload(
                task_id="task-123",
                document_id="doc-456",
                status="processing",
                progress=101
            )


@pytest.mark.asyncio
class TestWebhookDelivery:
    """Test webhook delivery to backend"""

    @respx.mock
    async def test_successful_webhook_delivery(self):
        """Test successful webhook delivery with 200 response"""
        # Mock the backend webhook endpoint
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback").mock(
            return_value=httpx.Response(200, json={
                "message": "Webhook processed successfully",
                "document_id": "doc-456",
                "status": "completed"
            })
        )

        client = WebhookClient("http://backend:8000", "secret")

        result = await client.send_webhook(
            task_id="task-123",
            document_id="doc-456",
            status="completed",
            result={"text": "content", "confidence": 95.0}
        )

        assert result is True
        assert route.called

        # Verify request had correct headers
        request = route.calls.last.request
        assert request.headers["Content-Type"] == "application/json"
        assert "X-Webhook-Signature" in request.headers

    @respx.mock
    async def test_successful_progress_webhook_delivery(self):
        """Test successful delivery of progress update webhook (Task 5.2)"""
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback").mock(
            return_value=httpx.Response(200, json={
                "message": "Webhook processed successfully",
                "document_id": "doc-456",
                "status": "processing"
            })
        )

        client = WebhookClient("http://backend:8000", "secret")

        result = await client.send_webhook(
            task_id="task-123",
            document_id="doc-456",
            status="processing",
            progress=45,
            current_operation="Performing OCR on page 5/10"
        )

        assert result is True
        assert route.called

        # Verify payload contains progress information
        request = route.calls.last.request
        payload = json.loads(request.content)
        assert payload["status"] == "processing"
        assert payload["progress"] == 45
        assert payload["current_operation"] == "Performing OCR on page 5/10"
        assert "result" not in payload
        assert "error" not in payload

    @respx.mock
    async def test_webhook_delivery_includes_signature_header(self):
        """Test that webhook requests include X-Webhook-Signature header"""
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback").mock(
            return_value=httpx.Response(200, json={"message": "OK"})
        )

        client = WebhookClient("http://backend:8000", "test-secret")

        await client.send_webhook(
            task_id="task-123",
            document_id="doc-456",
            status="completed",
            result={"text": "content"}
        )

        request = route.calls.last.request
        signature = request.headers["X-Webhook-Signature"]

        # Verify signature is valid hex string
        assert isinstance(signature, str)
        assert len(signature) == 64

        # Verify signature is correct
        payload_bytes = request.content
        expected_sig = hmac.new(
            "test-secret".encode(),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        assert signature == expected_sig

    @respx.mock
    async def test_webhook_delivery_with_timeout(self):
        """Test webhook delivery handles timeout errors and retries"""
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback").mock(
            side_effect=httpx.TimeoutException("Request timeout")
        )

        client = WebhookClient("http://backend:8000", "secret", timeout=1, max_retries=2)

        with patch('asyncio.sleep'):
            with pytest.raises(WebhookDeliveryError, match="after 2 retries"):
                await client.send_webhook(
                    task_id="task-123",
                    document_id="doc-456",
                    status="completed",
                    result={"text": "content"}
                )

        # Should retry: initial + 2 retries = 3 attempts
        assert route.call_count == 3

    @respx.mock
    async def test_webhook_delivery_with_connection_error(self):
        """Test webhook delivery handles connection errors and retries"""
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        client = WebhookClient("http://backend:8000", "secret", max_retries=2)

        with patch('asyncio.sleep'):
            with pytest.raises(WebhookDeliveryError, match="after 2 retries"):
                await client.send_webhook(
                    task_id="task-123",
                    document_id="doc-456",
                    status="completed",
                    result={"text": "content"}
                )

        # Should retry: initial + 2 retries = 3 attempts
        assert route.call_count == 3

    @respx.mock
    async def test_webhook_delivery_with_4xx_error(self):
        """Test webhook delivery handles 4xx client errors"""
        respx.post("http://backend:8000/api/webhooks/ocr/callback").mock(
            return_value=httpx.Response(400, json={
                "error": "Invalid payload"
            })
        )

        client = WebhookClient("http://backend:8000", "secret")

        with pytest.raises(WebhookDeliveryError, match="400"):
            await client.send_webhook(
                task_id="task-123",
                document_id="doc-456",
                status="completed",
                result={"text": "content"}
            )

    @respx.mock
    async def test_webhook_delivery_with_5xx_error(self):
        """Test webhook delivery handles 5xx server errors and retries"""
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback").mock(
            return_value=httpx.Response(500, json={
                "error": "Internal server error"
            })
        )

        client = WebhookClient("http://backend:8000", "secret", max_retries=2)

        with patch('asyncio.sleep'):
            with pytest.raises(WebhookDeliveryError, match="after 2 retries"):
                await client.send_webhook(
                    task_id="task-123",
                    document_id="doc-456",
                    status="completed",
                    result={"text": "content"}
                )

        # Should retry: initial + 2 retries = 3 attempts
        assert route.call_count == 3


@pytest.mark.asyncio
class TestWebhookRetryLogic:
    """Test webhook retry logic with exponential backoff"""

    @respx.mock
    async def test_retries_on_failure_with_exponential_backoff(self):
        """Test that client retries failed requests with exponential backoff"""
        # First two attempts fail, third succeeds
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback")
        route.side_effect = [
            httpx.Response(500, json={"error": "Server error"}),
            httpx.Response(500, json={"error": "Server error"}),
            httpx.Response(200, json={"message": "Success"})
        ]

        client = WebhookClient("http://backend:8000", "secret", max_retries=3)

        with patch('asyncio.sleep') as mock_sleep:
            result = await client.send_webhook(
                task_id="task-123",
                document_id="doc-456",
                status="completed",
                result={"text": "content"}
            )

        assert result is True
        assert route.call_count == 3

        # Verify exponential backoff was used (1s, 5s)
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 1  # First retry: 1 second
        assert mock_sleep.call_args_list[1][0][0] == 5  # Second retry: 5 seconds

    @respx.mock
    async def test_retries_exhaust_after_max_attempts(self):
        """Test that retries stop after max_retries is reached"""
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback").mock(
            return_value=httpx.Response(500, json={"error": "Server error"})
        )

        client = WebhookClient("http://backend:8000", "secret", max_retries=3)

        with patch('asyncio.sleep'):
            with pytest.raises(WebhookDeliveryError, match="after 3 retries"):
                await client.send_webhook(
                    task_id="task-123",
                    document_id="doc-456",
                    status="completed",
                    result={"text": "content"}
                )

        # Should attempt: initial + 3 retries = 4 total
        assert route.call_count == 4

    @respx.mock
    async def test_does_not_retry_on_4xx_errors(self):
        """Test that 4xx errors are not retried (client errors are permanent)"""
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback").mock(
            return_value=httpx.Response(400, json={"error": "Bad request"})
        )

        client = WebhookClient("http://backend:8000", "secret", max_retries=3)

        with pytest.raises(WebhookDeliveryError):
            await client.send_webhook(
                task_id="task-123",
                document_id="doc-456",
                status="completed",
                result={"text": "content"}
            )

        # Should only attempt once (no retries for 4xx)
        assert route.call_count == 1

    @respx.mock
    async def test_retries_on_timeout_errors(self):
        """Test that timeout errors trigger retries"""
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback")
        route.side_effect = [
            httpx.TimeoutException("Timeout"),
            httpx.Response(200, json={"message": "Success"})
        ]

        client = WebhookClient("http://backend:8000", "secret", max_retries=3)

        with patch('asyncio.sleep'):
            result = await client.send_webhook(
                task_id="task-123",
                document_id="doc-456",
                status="completed",
                result={"text": "content"}
            )

        assert result is True
        assert route.call_count == 2

    @respx.mock
    async def test_uses_correct_backoff_intervals(self):
        """Test that retry uses correct exponential backoff intervals: 1s, 5s, 15s"""
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback")
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(200, json={"message": "Success"})
        ]

        client = WebhookClient("http://backend:8000", "secret", max_retries=3)

        with patch('asyncio.sleep') as mock_sleep:
            await client.send_webhook(
                task_id="task-123",
                document_id="doc-456",
                status="completed",
                result={"text": "content"}
            )

        # Verify backoff intervals: 1s, 5s, 15s
        assert mock_sleep.call_count == 3
        assert mock_sleep.call_args_list[0][0][0] == 1
        assert mock_sleep.call_args_list[1][0][0] == 5
        assert mock_sleep.call_args_list[2][0][0] == 15


@pytest.mark.asyncio
class TestWebhookLogging:
    """Test webhook client logging"""

    @respx.mock
    async def test_logs_successful_delivery(self):
        """Test that successful deliveries are logged"""
        respx.post("http://backend:8000/api/webhooks/ocr/callback").mock(
            return_value=httpx.Response(200, json={"message": "OK"})
        )

        with patch('app.webhook_client.logger') as mock_logger:
            client = WebhookClient("http://backend:8000", "secret")

            await client.send_webhook(
                task_id="task-123",
                document_id="doc-456",
                status="completed",
                result={"text": "content"}
            )

            # Verify success was logged
            mock_logger.info.assert_called()
            call_args = str(mock_logger.info.call_args)
            assert "task-123" in call_args
            assert "doc-456" in call_args

    @respx.mock
    async def test_logs_retry_attempts(self):
        """Test that retry attempts are logged"""
        route = respx.post("http://backend:8000/api/webhooks/ocr/callback")
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(200, json={"message": "OK"})
        ]

        with patch('app.webhook_client.logger') as mock_logger:
            with patch('asyncio.sleep'):
                client = WebhookClient("http://backend:8000", "secret", max_retries=3)

                await client.send_webhook(
                    task_id="task-123",
                    document_id="doc-456",
                    status="completed",
                    result={"text": "content"}
                )

                # Verify retry was logged
                mock_logger.warning.assert_called()
                call_args = str(mock_logger.warning.call_args_list)
                assert "retry" in call_args.lower()

    @respx.mock
    async def test_logs_final_failure(self):
        """Test that final failures are logged as errors"""
        respx.post("http://backend:8000/api/webhooks/ocr/callback").mock(
            return_value=httpx.Response(500, json={"error": "Server error"})
        )

        with patch('app.webhook_client.logger') as mock_logger:
            with patch('asyncio.sleep'):
                client = WebhookClient("http://backend:8000", "secret", max_retries=2)

                with pytest.raises(WebhookDeliveryError):
                    await client.send_webhook(
                        task_id="task-123",
                        document_id="doc-456",
                        status="completed",
                        result={"text": "content"}
                    )

                # Verify error was logged
                mock_logger.error.assert_called()


class TestWebhookClientContextManager:
    """Test webhook client as async context manager"""

    @pytest.mark.asyncio
    async def test_client_works_as_async_context_manager(self):
        """Test that WebhookClient can be used as async context manager"""
        async with WebhookClient("http://backend:8000", "secret") as client:
            assert client is not None
            assert hasattr(client, 'send_webhook')

    @pytest.mark.asyncio
    async def test_client_closes_http_client_on_exit(self):
        """Test that HTTP client is properly closed when exiting context"""
        client = WebhookClient("http://backend:8000", "secret")

        async with client:
            # Client should have an HTTP client
            assert hasattr(client, '_http_client')
            http_client = client._http_client

        # HTTP client should be closed after context exit
        assert http_client.is_closed


class TestWebhookClientConfiguration:
    """Test webhook client configuration from environment"""

    @patch.dict('os.environ', {
        'BACKEND_URL': 'http://custom-backend:9000',
        'OCR_WEBHOOK_SECRET': 'env-secret-key',
        'WEBHOOK_TIMEOUT': '60',
        'WEBHOOK_MAX_RETRIES': '5'
    })
    def test_client_loads_config_from_environment(self):
        """Test that client can load configuration from environment variables"""
        client = WebhookClient.from_env()

        assert client.backend_url == "http://custom-backend:9000"
        assert client.webhook_secret == "env-secret-key"
        assert client.timeout == 60
        assert client.max_retries == 5

    @patch.dict('os.environ', {}, clear=True)
    def test_client_raises_error_if_env_vars_missing(self):
        """Test that client raises error if required env vars are missing"""
        with pytest.raises(ValueError, match="BACKEND_URL"):
            WebhookClient.from_env()
