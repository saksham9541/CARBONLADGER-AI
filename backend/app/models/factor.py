"""
CarbonLedger AI — Emission Factor Registry Models
=================================================
Approved factor versions, individual activity factors, and formal approval sign-offs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ApprovalDecision, FactorVersionStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FactorVersion(Base):
    """
    Container for an uploaded, versioned emission factor dataset (e.g. CEA v22.0 or UK DESNZ 2026).
    Factors are only eligible for calculation once the version status is APPROVED.
    """
    __tablename__ = "factor_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)  # CEA | UK-DESNZ | EPA
    version: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "22.0"
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    geography: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "India", "UK"
    status: Mapped[str] = mapped_column(
        String(50), default=FactorVersionStatus.PENDING.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    factors: Mapped[List["EmissionFactor"]] = relationship(
        "EmissionFactor", back_populates="version", cascade="all, delete-orphan"
    )
    approvals: Mapped[List["FactorApproval"]] = relationship(
        "FactorApproval", back_populates="version", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("org_id", "source", "version", "year", name="uq_org_factor_version"),
        Index("ix_factor_versions_status", "org_id", "status"),
    )


class EmissionFactor(Base):
    """
    Individual activity-to-emission factor.
    Deterministic arithmetic uses `value` and validates `factor_unit`.
    """
    __tablename__ = "emission_factors"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("factor_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    factor_id: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. GRID-IN-2026-01
    activity: Mapped[str] = mapped_column(String(255), nullable=False)   # Purchased electricity
    value: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    factor_unit: Mapped[str] = mapped_column(String(50), nullable=False)  # kg CO2e/kWh
    gas_type: Mapped[str] = mapped_column(String(50), default="CO2e", nullable=False)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)  # "1", "2", "3"
    source_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    methodology: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    version: Mapped["FactorVersion"] = relationship("FactorVersion", back_populates="factors")

    __table_args__ = (
        Index("ix_factors_activity_scope", "org_id", "activity", "scope"),
    )


class FactorApproval(Base):
    """
    Formal sign-off by a privileged user (Admin or certified Auditor) approving a factor version.
    """
    __tablename__ = "factor_approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("factor_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approved_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(
        String(50), default=ApprovalDecision.APPROVED.value, nullable=False
    )
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    version: Mapped["FactorVersion"] = relationship("FactorVersion", back_populates="approvals")
