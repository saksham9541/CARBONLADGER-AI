"""
CarbonLedger AI — Reporting Periods Router
==========================================
Accounting interval management with strict organization isolation.
"""

import uuid
from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_analyst_or_admin, require_any_member
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.organization import OrganizationMembership
from app.models.reporting_period import ReportingPeriod
from app.schemas.reporting_period import (
    ReportingPeriodCreate,
    ReportingPeriodResponse,
    ReportingPeriodUpdate,
)

router = APIRouter(prefix="/organizations/{org_id}/reporting-periods", tags=["Reporting Periods"])
logger = get_logger(__name__)


@router.post(
    "",
    response_model=ReportingPeriodResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a reporting period",
    description="Requires Analyst or Admin role in the organization. Auditors have read-only access.",
)
def create_reporting_period(
    org_id: UUID,
    payload: ReportingPeriodCreate,
    _membership: OrganizationMembership = Depends(require_analyst_or_admin),
    db: Session = Depends(get_db),
) -> ReportingPeriodResponse:
    # Check for name collision within this organization
    existing = db.execute(
        select(ReportingPeriod).where(
            ReportingPeriod.org_id == org_id,
            ReportingPeriod.name == payload.name,
        )
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A reporting period named '{payload.name}' already exists in this organization",
        )

    period = ReportingPeriod(
        org_id=org_id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        boundary_id=payload.boundary_id,
    )
    db.add(period)
    db.commit()
    db.refresh(period)

    logger.info(
        "Reporting period created",
        period_id=str(period.id),
        org_id=str(org_id),
        name=period.name,
    )
    return ReportingPeriodResponse.model_validate(period)


@router.get(
    "",
    response_model=List[ReportingPeriodResponse],
    summary="List organization reporting periods",
    description="Returns all reporting intervals for the organization. Requires active membership.",
)
def list_reporting_periods(
    org_id: UUID,
    _membership: OrganizationMembership = Depends(require_any_member),
    db: Session = Depends(get_db),
) -> List[ReportingPeriodResponse]:
    # Strictly scoped by org_id
    periods = db.execute(
        select(ReportingPeriod)
        .where(ReportingPeriod.org_id == org_id)
        .order_by(ReportingPeriod.start_date.desc())
    ).scalars().all()
    return [ReportingPeriodResponse.model_validate(p) for p in periods]


@router.get(
    "/{period_id}",
    response_model=ReportingPeriodResponse,
    summary="Get single reporting period",
    description="Requires active membership. Strictly scoped to the organization.",
)
def get_reporting_period(
    org_id: UUID,
    period_id: UUID,
    _membership: OrganizationMembership = Depends(require_any_member),
    db: Session = Depends(get_db),
) -> ReportingPeriodResponse:
    # Query must match both org_id AND period_id to ensure tenant isolation
    period = db.execute(
        select(ReportingPeriod).where(
            ReportingPeriod.org_id == org_id,
            ReportingPeriod.id == period_id,
        )
    ).scalar_one_or_none()

    if not period:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reporting period '{period_id}' not found in this organization",
        )

    return ReportingPeriodResponse.model_validate(period)


@router.patch(
    "/{period_id}",
    response_model=ReportingPeriodResponse,
    summary="Update reporting period",
    description="Requires Analyst or Admin role in the organization.",
)
def update_reporting_period(
    org_id: UUID,
    period_id: UUID,
    payload: ReportingPeriodUpdate,
    _membership: OrganizationMembership = Depends(require_analyst_or_admin),
    db: Session = Depends(get_db),
) -> ReportingPeriodResponse:
    period = db.execute(
        select(ReportingPeriod).where(
            ReportingPeriod.org_id == org_id,
            ReportingPeriod.id == period_id,
        )
    ).scalar_one_or_none()

    if not period:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reporting period '{period_id}' not found in this organization",
        )

    if payload.name is not None:
        period.name = payload.name
    if payload.start_date is not None:
        period.start_date = payload.start_date
    if payload.end_date is not None:
        period.end_date = payload.end_date
    if payload.status is not None:
        period.status = payload.status.value

    db.commit()
    db.refresh(period)
    return ReportingPeriodResponse.model_validate(period)
