"""
CarbonLedger AI — Centralized Exception Handling
=================================================
All HTTP errors are returned as structured JSON with a consistent schema.
Unexpected exceptions are logged with full context and returned as 500.
"""

from __future__ import annotations

import traceback
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger(__name__)


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: str
    errors: Optional[list[ErrorDetail]] = None
    request_id: Optional[str] = None


class CarbonLedgerError(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(message)


class EvidenceNotFoundError(CarbonLedgerError):
    def __init__(self, evidence_id: str) -> None:
        super().__init__(
            message=f"Evidence file '{evidence_id}' not found.",
            code="EVIDENCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class FactorNotFoundError(CarbonLedgerError):
    def __init__(self, factor_id: str) -> None:
        super().__init__(
            message=f"Emission factor '{factor_id}' not found or not approved.",
            code="FACTOR_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class MissingEvidenceError(CarbonLedgerError):
    """Raised when required evidence is absent for a reporting interval."""

    def __init__(self, interval: str) -> None:
        super().__init__(
            message=f"Required evidence is missing for interval: {interval}. "
                    "The system will not silently estimate or fill missing data.",
            code="MISSING_EVIDENCE",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class UnitConversionError(CarbonLedgerError):
    """Raised when a unit conversion is not registered or would be unsafe."""

    def __init__(self, from_unit: str, to_unit: str, reason: str = "") -> None:
        super().__init__(
            message=f"Cannot convert '{from_unit}' to '{to_unit}'. {reason}",
            code="UNIT_CONVERSION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class CalculationBlockedError(CarbonLedgerError):
    """Raised when calculation is blocked due to missing or unapproved factors."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Calculation blocked: {reason}",
            code="CALCULATION_BLOCKED",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application."""

    @app.exception_handler(CarbonLedgerError)
    async def carbonledger_error_handler(
        request: Request, exc: CarbonLedgerError
    ) -> JSONResponse:
        logger.warning(
            "Application error",
            code=exc.code,
            message=exc.message,
            path=str(request.url),
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "detail": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            ErrorDetail(
                code="VALIDATION_ERROR",
                message=str(e["msg"]),
                field=".".join(str(loc) for loc in e.get("loc", [])),
            ).model_dump()
            for e in exc.errors()
        ]
        logger.warning(
            "Request validation failed",
            path=str(request.url),
            errors=errors,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "VALIDATION_ERROR", "detail": "Request validation failed.", "errors": errors},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "Unhandled exception",
            path=str(request.url),
            exc_type=type(exc).__name__,
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "detail": "An unexpected error occurred. Please contact support.",
            },
        )
