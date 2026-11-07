"""
CarbonLedger AI — Calculations, Worksheets & Exceptions
=======================================================
Deterministic carbon arithmetic records (immutable), worksheet freeze snapshots,
and evidence gap/conflict tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import ExceptionFlagType, ExceptionStatus, WorksheetStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Calculation(Base):
    """
    Immutable record of a deterministic emission calculation.
    Formula: Activity Quantity (normalised) × Emission Factor = Emissions (kg CO2e)
    All inputs, formulas, and results are permanently captured.
    """
    __tablename__ = "calculations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reporting_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("activity_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    factor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("emission_factors.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Operands captured at calculation time
    activity_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    activity_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    factor_value: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    factor_unit: Mapped[str] = mapped_column(String(50), nullable=False)

    # Exact decimal outputs
    emissions_kg_co2e: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    emissions_t_co2e: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)  # "1", "2", "3"

    formula: Mapped[str] = mapped_column(String(255), nullable=False)      # e.g. "2500 kWh * 0.70000000 kg CO2e/kWh"
    calc_version: Mapped[str] = mapped_column(String(50), nullable=False) # e.g. "engine-v1.0.0"

    calculated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        Index("ix_calculations_period_scope", "org_id", "period_id", "scope"),
    )


class WorksheetVersion(Base):
    """
    Frozen snapshot of a complete accounting period worksheet for review & sign-off.
    """
    __tablename__ = "worksheet_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reporting_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    total_emissions_t_co2e: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    scope1_t_co2e: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    scope2_t_co2e: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    scope3_t_co2e: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=WorksheetStatus.DRAFT.value, nullable=False
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        Index("ix_worksheet_versions_period", "org_id", "period_id", "version_number"),
    )


class EvidenceException(Base):
    """
    Tracks data anomalies: missing months, duplicate bills, unit mismatches, or unapproved factors.
    Prevents silent fabrication or gap-filling.
    """
    __tablename__ = "evidence_exceptions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reporting_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flag_type: Mapped[str] = mapped_column(
        String(50), default=ExceptionFlagType.MISSING_EVIDENCE.value, nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("activity_records.id", ondelete="SET NULL"), nullable=True
    )
    file_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("evidence_files.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(50), default=ExceptionStatus.OPEN.value, nullable=False
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        Index("ix_evidence_exceptions_period_status", "org_id", "period_id", "status"),
    )
