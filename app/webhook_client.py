"""
Webhook Client for OCR Service
Sends webhook notifications to backend when OCR processing completes
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import httpx


# Configure logging
logger = logging.getLogger(__name__)


class WebhookDeliveryError(Exception):
    """Exception raised when webhook delivery fails"""
    pass


class WebhookSignatureError(Exception):
    """Exception raised when webhook signature is invalid"""
    pass


class WebhookClient:
    """
    HTTP client for sending webhook notifications to backend

    Features:
    - HMAC-SHA256 signature generation for security
    - Exponential backoff retry logic (1s, 5s, 15s)
    - Async context manager for resource cleanup
    - Configurable timeout and retry settings
    """

    def __init__(
        self,
        backend_url: str,
        webhook_secret: str,
        max_retries: int = 3,
        timeout: int = 30
    ):
        """
        Initialize webhook client

        Args:
            backend_url: Base URL of the backend service
            webhook_secret: Secret key for HMAC signature generation
            max_retries: Maximum number of retry attempts (default: 3)
            timeout: Request timeout in seconds (default: 30)

        Raises:
            ValueError: If backend_url is invalid or webhook_secret is empty
        """
        # Validate backend URL
        if not backend_url:
            raise ValueError("Invalid backend URL")

        try:
            parsed = urlparse(backend_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid backend URL")
        except Exception:
            raise ValueError("Invalid backend URL")

        # Validate webhook secret
        if not webhook_secret or not webhook_secret.strip():
            raise ValueError("Webhook secret is required")

        self.backend_url = backend_url.rstrip('/')
        self.webhook_secret = webhook_secret
        self.max_retries = max_retries
        self.timeout = timeout
        self._http_client: Optional[httpx.AsyncClient] = None

    @classmethod
    def from_env(cls) -> 'WebhookClient':
        """
        Create WebhookClient from environment variables

        Environment variables:
            BACKEND_URL: Backend service URL
            OCR_WEBHOOK_SECRET: Webhook secret key
            WEBHOOK_TIMEOUT: Request timeout (optional, default: 30)
            WEBHOOK_MAX_RETRIES: Max retry attempts (optional, default: 3)

        Returns:
            WebhookClient instance

        Raises:
            ValueError: If required environment variables are missing
        """
        backend_url = os.getenv('BACKEND_URL')
        if not backend_url:
            raise ValueError("BACKEND_URL environment variable is required")

        webhook_secret = os.getenv('OCR_WEBHOOK_SECRET')
        if not webhook_secret:
            raise ValueError("OCR_WEBHOOK_SECRET environment variable is required")

        timeout = int(os.getenv('WEBHOOK_TIMEOUT', '30'))
        max_retries = int(os.getenv('WEBHOOK_MAX_RETRIES', '3'))

        return cls(
            backend_url=backend_url,
            webhook_secret=webhook_secret,
            max_retries=max_retries,
            timeout=timeout
        )

    def _generate_signature(self, payload: str) -> str:
        """
        Generate HMAC-SHA256 signature for webhook payload

        Args:
            payload: JSON string of the webhook payload

        Returns:
            Hex-encoded HMAC signature
        """
        signature = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _build_payload(
        self,
        task_id: str,
        document_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        progress: Optional[int] = None,
        current_operation: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build webhook payload

        Args:
            task_id: OCR task ID
            document_id: Document ID
            status: Processing status (completed, failed, processing)
            result: OCR result data (for completed status)
            error: Error message (for failed status)
            progress: Progress percentage 0-100 (for processing status)
            current_operation: Current operation description (for processing status)

        Returns:
            Webhook payload dictionary

        Raises:
            ValueError: If progress is not between 0 and 100
        """
        # Validate progress if provided
        if progress is not None and (progress < 0 or progress > 100):
            raise ValueError("Progress must be between 0 and 100")

        payload = {
            'task_id': task_id,
            'document_id': document_id,
            'status': status,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

        if status == 'completed' and result:
            payload['result'] = result

        if status == 'failed' and error:
            payload['error'] = error

        # Add progress tracking for processing status
        if progress is not None:
            payload['progress'] = progress

        if current_operation is not None:
            payload['current_operation'] = current_operation

        return payload

    async def send_webhook(
        self,
        task_id: str,
        document_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        progress: Optional[int] = None,
        current_operation: Optional[str] = None
    ) -> bool:
        """
        Send webhook notification to backend

        Args:
            task_id: OCR task ID
            document_id: Document ID
            status: Processing status (completed, failed, processing)
            result: OCR result data (for completed status)
            error: Error message (for failed status)
            progress: Progress percentage 0-100 (for processing status)
            current_operation: Current operation description (for processing status)

        Returns:
            True if webhook was delivered successfully

        Raises:
            WebhookDeliveryError: If webhook delivery fails after all retries
        """
        # Build payload
        payload = self._build_payload(
            task_id=task_id,
            document_id=document_id,
            status=status,
            result=result,
            error=error,
            progress=progress,
            current_operation=current_operation
        )

        # Convert to JSON
        payload_json = json.dumps(payload, separators=(',', ':'))

        # Generate signature
        signature = self._generate_signature(payload_json)

        # Prepare headers
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Signature': signature
        }

        # Build webhook URL
        webhook_url = f"{self.backend_url}/api/webhooks/ocr/callback"

        # Ensure HTTP client is initialized
        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)

        # Retry logic with exponential backoff
        backoff_intervals = [1, 5, 15]  # seconds
        last_error = None
        delivery_start_time = datetime.now()

        for attempt in range(self.max_retries + 1):
            try:
                attempt_start_time = datetime.now()

                logger.info(
                    f"Sending webhook to backend",
                    extra={
                        'task_id': task_id,
                        'document_id': document_id,
                        'status': status,
                        'attempt': attempt + 1,
                        'max_retries': self.max_retries
                    }
                )

                response = await self._http_client.post(
                    webhook_url,
                    content=payload_json,
                    headers=headers
                )

                attempt_latency = (datetime.now() - attempt_start_time).total_seconds() * 1000
                total_latency = (datetime.now() - delivery_start_time).total_seconds() * 1000

                # Check response status
                if response.status_code == 200:
                    logger.info(
                        f"Webhook delivered successfully",
                        extra={
                            'task_id': task_id,
                            'document_id': document_id,
                            'status': status,
                            'result': 'success',
                            'attempt': attempt + 1,
                            'attempt_latency_ms': round(attempt_latency, 2),
                            'total_latency_ms': round(total_latency, 2),
                            'http_status': response.status_code
                        }
                    )
                    return True

                # 4xx errors are permanent - don't retry
                if 400 <= response.status_code < 500:
                    error_msg = f"Webhook rejected with status {response.status_code}"
                    logger.error(
                        error_msg,
                        extra={
                            'task_id': task_id,
                            'document_id': document_id,
                            'result': 'error_client_error',
                            'http_status': response.status_code,
                            'attempt': attempt + 1,
                            'attempt_latency_ms': round(attempt_latency, 2),
                            'total_latency_ms': round(total_latency, 2),
                            'response_text': response.text[:200]  # First 200 chars
                        }
                    )
                    raise WebhookDeliveryError(error_msg)

                # Unexpected status code
                error_msg = f"Unexpected response status {response.status_code}"
                last_error = WebhookDeliveryError(error_msg)

                # 5xx errors are transient - retry
                if response.status_code >= 500:
                    error_msg = f"Backend error with status {response.status_code}"
                    last_error = WebhookDeliveryError(error_msg)

                    if attempt < self.max_retries:
                        backoff = backoff_intervals[attempt]
                        logger.warning(
                            f"Webhook delivery failed, retrying in {backoff}s",
                            extra={
                                'task_id': task_id,
                                'document_id': document_id,
                                'result': 'error_server_error_retrying',
                                'http_status': response.status_code,
                                'attempt': attempt + 1,
                                'attempt_latency_ms': round(attempt_latency, 2),
                                'total_latency_ms': round(total_latency, 2),
                                'backoff_seconds': backoff
                            }
                        )
                        await asyncio.sleep(backoff)
                        continue

            except httpx.TimeoutException as e:
                error_msg = f"Webhook request timeout: {str(e)}"
                last_error = WebhookDeliveryError(error_msg)

                if attempt < self.max_retries:
                    backoff = backoff_intervals[attempt]
                    logger.warning(
                        f"Webhook timeout, retrying in {backoff}s",
                        extra={
                            'task_id': task_id,
                            'document_id': document_id,
                            'attempt': attempt + 1,
                            'backoff': backoff
                        }
                    )
                    await asyncio.sleep(backoff)
                    continue

            except httpx.ConnectError as e:
                error_msg = f"Connection error: {str(e)}"
                last_error = WebhookDeliveryError(error_msg)

                if attempt < self.max_retries:
                    backoff = backoff_intervals[attempt]
                    logger.warning(
                        f"Connection error, retrying in {backoff}s",
                        extra={
                            'task_id': task_id,
                            'document_id': document_id,
                            'attempt': attempt + 1,
                            'backoff': backoff
                        }
                    )
                    await asyncio.sleep(backoff)
                    continue

            except WebhookDeliveryError:
                # Re-raise WebhookDeliveryError without retrying (permanent failures)
                raise

            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                last_error = WebhookDeliveryError(error_msg)

                if attempt < self.max_retries:
                    backoff = backoff_intervals[attempt]
                    logger.warning(
                        f"Unexpected error, retrying in {backoff}s",
                        extra={
                            'task_id': task_id,
                            'document_id': document_id,
                            'error': str(e),
                            'attempt': attempt + 1,
                            'backoff': backoff
                        }
                    )
                    await asyncio.sleep(backoff)
                    continue

        # All retries exhausted
        total_latency = (datetime.now() - delivery_start_time).total_seconds() * 1000
        final_error_msg = f"Webhook delivery failed after {self.max_retries} retries"
        logger.error(
            final_error_msg,
            extra={
                'task_id': task_id,
                'document_id': document_id,
                'result': 'error_retries_exhausted',
                'total_attempts': self.max_retries + 1,
                'total_latency_ms': round(total_latency, 2),
                'last_error': str(last_error) if last_error else 'Unknown'
            }
        )

        # Re-raise with message indicating retries exhausted
        raise WebhookDeliveryError(final_error_msg)

    async def __aenter__(self) -> 'WebhookClient':
        """Enter async context manager"""
        self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager and cleanup resources"""
        if self._http_client:
            await self._http_client.aclose()
