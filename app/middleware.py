"""
Middleware for global error handling and request processing
"""
import logging
import uuid
import json
from typing import Callable
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime

from .models import ErrorResponse


logger = logging.getLogger(__name__)


async def error_middleware(request: Request, call_next: Callable):
    """
    Global error handling middleware

    Catches uncaught exceptions and formats them consistently

    Args:
        request: FastAPI request
        call_next: Next middleware/endpoint

    Returns:
        Response with error handling
    """
    # Generate request ID for tracing
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    try:
        # Add request ID to request state
        request.state.request_id = request_id

        # Call next middleware/endpoint
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response

    except HTTPException as exc:
        # FastAPI HTTP exceptions - pass through with request ID
        logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail} [Request ID: {request_id}]")

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail if isinstance(exc.detail, str) else exc.detail.get("error", "Error"),
                "detail": exc.detail if isinstance(exc.detail, str) else exc.detail.get("detail"),
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    except RequestValidationError as exc:
        # Pydantic validation errors
        logger.warning(f"Validation error: {exc.errors()} [Request ID: {request_id}]")

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation error",
                "detail": exc.errors(),
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    except Exception as exc:
        # Uncaught exceptions
        logger.error(
            f"Unhandled exception: {type(exc).__name__}: {str(exc)} [Request ID: {request_id}]",
            exc_info=True
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "detail": "An unexpected error occurred. Please contact support with request ID.",
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging all requests"""

    async def dispatch(self, request: Request, call_next: Callable):
        """
        Log request and response information

        Args:
            request: FastAPI request
            call_next: Next middleware/endpoint

        Returns:
            Response
        """
        # Log request
        request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
        start_time = datetime.utcnow()

        logger.info(
            f"Request started: {request.method} {request.url.path} [Request ID: {request_id}]"
        )

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds()

        # Log response
        logger.info(
            f"Request completed: {request.method} {request.url.path} "
            f"Status: {response.status_code} Duration: {duration:.3f}s [Request ID: {request_id}]"
        )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple rate limiting middleware

    In production, use Redis-based rate limiting
    """

    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        """
        Initialize rate limiter

        Args:
            app: FastAPI application
            max_requests: Maximum requests per window
            window_seconds: Time window in seconds
        """
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.request_counts: dict = {}  # In-memory store (use Redis in production)

    async def dispatch(self, request: Request, call_next: Callable):
        """
        Check rate limits and process request

        Args:
            request: FastAPI request
            call_next: Next middleware/endpoint

        Returns:
            Response or rate limit error
        """
        # Get client identifier (IP or API key)
        client_id = self._get_client_id(request)

        # Check rate limit
        if self._is_rate_limited(client_id):
            logger.warning(f"Rate limit exceeded for client {client_id}")

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Maximum {self.max_requests} requests per {self.window_seconds} seconds",
                    "retry_after": self.window_seconds
                },
                headers={"Retry-After": str(self.window_seconds)}
            )

        # Process request
        response = await call_next(request)

        return response

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request"""
        # Check for API key in headers
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"key:{api_key}"

        # Use client IP
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    def _is_rate_limited(self, client_id: str) -> bool:
        """
        Check if client has exceeded rate limit

        Args:
            client_id: Client identifier

        Returns:
            True if rate limited
        """
        now = datetime.utcnow().timestamp()
        window_start = now - self.window_seconds

        # Clean up old entries
        if client_id in self.request_counts:
            self.request_counts[client_id] = [
                ts for ts in self.request_counts[client_id]
                if ts > window_start
            ]
        else:
            self.request_counts[client_id] = []

        # Check limit
        if len(self.request_counts[client_id]) >= self.max_requests:
            return True

        # Add current request
        self.request_counts[client_id].append(now)
        return False


def setup_middleware(app):
    """
    Setup all middleware for the application

    Args:
        app: FastAPI application
    """
    # Add rate limiting
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=100,
        window_seconds=60
    )

    # Add request logging
    app.add_middleware(RequestLoggingMiddleware)

    # Error handling is added via middleware function in main.py
