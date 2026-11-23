"""
Custom Domain Exceptions and Global Exception Handlers for DropPrint Server.
Provides structured JSON error responses with clear status codes and error types.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class DropPrintError(Exception):
    """Base domain exception for DropPrint application."""

    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST, extra: Optional[Dict[str, Any]] = None):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.extra = extra or {}


class PricingError(DropPrintError):
    """Raised when pricing calculations or rate configurations are invalid."""

    def __init__(self, detail: str = "Invalid pricing parameters", status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(detail=detail, status_code=status_code)


class SpoolerError(DropPrintError):
    """Raised when hardware printer spooling fails or printer is unavailable."""

    def __init__(self, detail: str = "Printer hardware spooler error", status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        super().__init__(detail=detail, status_code=status_code)


class JobNotFoundError(DropPrintError):
    """Raised when a print job cannot be found with the given identifier."""

    def __init__(self, detail: str = "Print job not found", status_code: int = status.HTTP_404_NOT_FOUND):
        super().__init__(detail=detail, status_code=status_code)


class ShopNotFoundError(DropPrintError):
    """Raised when a shop cannot be found with the given shop_id."""

    def __init__(self, detail: str = "Shop not found", status_code: int = status.HTTP_404_NOT_FOUND):
        super().__init__(detail=detail, status_code=status_code)


class InvalidTransitionError(DropPrintError):
    """Raised when an invalid state machine transition is attempted."""

    def __init__(self, detail: str = "Invalid job state transition", status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(detail=detail, status_code=status_code)


class AuthenticationError(DropPrintError):
    """Raised when authentication credentials or session tokens are invalid."""

    def __init__(self, detail: str = "Authentication required or invalid credentials", status_code: int = status.HTTP_401_UNAUTHORIZED):
        super().__init__(detail=detail, status_code=status_code)


async def dropprint_exception_handler(request: Request, exc: DropPrintError) -> JSONResponse:
    """Handles all domain-specific DropPrintError exceptions."""
    logger.warning("Domain exception at %s %s: [%s] %s", request.method, request.url.path, exc.__class__.__name__, exc.detail)
    content: Dict[str, Any] = {
        "detail": exc.detail,
        "error": exc.__class__.__name__,
        "status_code": exc.status_code,
    }
    if exc.extra:
        content["extra"] = exc.extra
    return JSONResponse(status_code=exc.status_code, content=content)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handles standard FastAPI HTTPException with consistent JSON structure."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error": "HTTPException",
            "status_code": exc.status_code,
        },
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handles request validation errors (HTTP 422)."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "error": "ValidationError",
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registers standard structured JSON exception handlers on the FastAPI app."""
    app.add_exception_handler(DropPrintError, dropprint_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
