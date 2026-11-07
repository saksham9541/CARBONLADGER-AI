"""
CarbonLedger AI — Reporting Period Model
=========================================
Tracks emissions accounting timeframes with calendar boundaries.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ReportingPeriodStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReportingPeriod(Base):
    __tablename__ = "reporting_periods"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    boundary_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reporting_boundaries.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=ReportingPeriodStatus.DRAFT.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")  # noqa: F821
    boundary: Mapped[Optional["ReportingBoundary"]] = relationship("ReportingBoundary")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_org_period_name"),
        Index("ix_org_period_dates", "org_id", "start_date", "end_date"),
    )
