"""
CarbonLedger AI — Health Check Router
======================================
GET /api/health — public endpoint that returns the operational
status of the API and its dependent services.

This is intentionally lightweight: no authentication required,
no database writes, minimal latency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.schemas.health import HealthResponse, ServiceStatus

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()


def _check_database(db: Session) -> ServiceStatus:
    """Ping the database with a cheap query."""
    try:
        db.execute(text("SELECT 1"))
        return ServiceStatus.OK
    except Exception as exc:
        logger.warning("Database health check failed", exc=str(exc))
        return ServiceStatus.ERROR


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="API health check",
    description=(
        "Returns the operational status of the CarbonLedger AI backend. "
        "Safe to call without authentication."
    ),
    tags=["System"],
)
def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    """
    Public health endpoint.

    Returns:
    - **status**: Overall API health (ok | degraded | error)
    - **version**: Application version
    - **timestamp**: UTC ISO-8601 timestamp
    - **environment**: Runtime environment name
    - **services**: Individual service statuses
    """
    db_status = _check_database(db)

    services: Dict[str, ServiceStatus] = {
        "database": db_status,
        "storage": ServiceStatus.UNCONFIGURED if not settings.supabase_url else ServiceStatus.OK,
        "gemini": ServiceStatus.UNCONFIGURED if not settings.gemini_api_key else ServiceStatus.OK,
    }

    # Overall status is the worst of all individual statuses
    all_statuses = list(services.values())
    if ServiceStatus.ERROR in all_statuses:
        overall = ServiceStatus.DEGRADED
    else:
        overall = ServiceStatus.OK

    logger.info("Health check", status=overall, services={k: v for k, v in services.items()})

    return HealthResponse(
        status=overall,
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        environment=settings.environment,
        services=services,
    )
