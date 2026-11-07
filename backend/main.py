"""
CarbonLedger AI — FastAPI Application Entry Point
==================================================
Wires together:
  - Settings and structured logging
  - CORS middleware (configurable origins)
  - Centralized exception handlers
  - API routers (versioned under /api)
  - OpenAPI documentation (disabled in production)

DESIGN RULE: AI never performs carbon arithmetic.
All calculations run in the deterministic Python engine
(app/services/calculator.py) using Python Decimal and
versioned, approved emission factor tables.
"""

from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import health, organizations, reporting_periods
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger

# ── Bootstrap ────────────────────────────────────────────────
configure_logging()
settings = get_settings()
logger = get_logger(__name__)


# ── FastAPI application ───────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "CarbonLedger AI — Auditable, evidence-driven carbon accounting platform.\n\n"
        "**Core rule**: The AI layer (Gemini) performs document extraction only. "
        "All carbon arithmetic uses the deterministic Python calculation engine "
        "with approved, versioned emission factors. No LLM performs calculations."
    ),
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
)


# ── Middleware ────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Exception handlers ────────────────────────────────────────
register_exception_handlers(app)


# ── Routers ───────────────────────────────────────────────────
app.include_router(health.router, prefix="/api")
app.include_router(organizations.router, prefix="/api")
app.include_router(reporting_periods.router, prefix="/api")

# Phase 2+ routers will be registered here:
# app.include_router(evidence.router, prefix="/api/evidence", tags=["Evidence"])
# app.include_router(extraction.router, prefix="/api/extraction", tags=["Extraction"])
# app.include_router(activities.router, prefix="/api/activities", tags=["Activities"])
# app.include_router(factors.router, prefix="/api/factors", tags=["Factors"])
# app.include_router(calculations.router, prefix="/api/calculations", tags=["Calculations"])
# app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
# app.include_router(audit.router, prefix="/api/audit", tags=["Audit"])


# ── Lifecycle events ──────────────────────────────────────────
@app.on_event("startup")
async def on_startup() -> None:
    logger.info(
        "CarbonLedger AI starting",
        version=settings.app_version,
        environment=settings.environment,
        cors_origins=settings.cors_origins_list,
    )


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("CarbonLedger AI shutting down")
