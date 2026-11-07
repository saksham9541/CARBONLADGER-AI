"""
CarbonLedger AI — Report Generation & Sign-off Models
=====================================================
Formal greenhouse gas inventory reports, exports, and digital sign-offs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ApprovalDecision, ReportStatus, ReportType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Report(Base):
    """
    Generated audit report (PDF, Excel, or JSON package).
    AI commentary is separated from deterministic arithmetic figures.
    """
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reporting_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    worksheet_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("worksheet_versions.id", ondelete="SET NULL"), nullable=True
    )
    report_type: Mapped[str] = mapped_column(
        String(50), default=ReportType.FULL_INVENTORY.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), default=ReportStatus.DRAFT.value, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    summary_narrative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    approvals: Mapped[List["ReportApproval"]] = relationship(
        "ReportApproval", back_populates="report", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_reports_org_period_status", "org_id", "period_id", "status"),
    )


class ReportApproval(Base):
    """
    Formal sign-off by designated lead analyst or auditor before publishing.
    """
    __tablename__ = "report_approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True
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

    report: Mapped["Report"] = relationship("Report", back_populates="approvals")
