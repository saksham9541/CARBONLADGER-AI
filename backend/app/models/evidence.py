"""
CarbonLedger AI — Evidence & Activity Data Models
=================================================
Evidence Files (immutable originals), AI Extraction Jobs, Activity Records,
and Human Correction Revisions.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.enums import ActivityRecordStatus, EvidenceFileType, ExtractionJobStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceFile(Base):
    """
    Original document metadata.
    Evidence files are immutable after upload (soft-delete only).
    """
    __tablename__ = "evidence_files"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reporting_periods.id", ondelete="SET NULL"), nullable=True, index=True
    )
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # SHA-256
    file_type: Mapped[str] = mapped_column(
        String(50), default=EvidenceFileType.PDF.value, nullable=False
    )
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    extraction_jobs: Mapped[List["ExtractionJob"]] = relationship(
        "ExtractionJob", back_populates="file", cascade="all, delete-orphan"
    )
    activity_records: Mapped[List["ActivityRecord"]] = relationship(
        "ActivityRecord", back_populates="file"
    )


class ExtractionJob(Base):
    """
    Tracks AI extraction executions and raw structured output.
    """
    __tablename__ = "extraction_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), default=ExtractionJobStatus.PENDING.value, nullable=False
    )
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    extracted_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    file: Mapped["EvidenceFile"] = relationship("EvidenceFile", back_populates="extraction_jobs")


class ActivityRecord(Base):
    """
    Granular activity entry extracted from evidence.
    Tracks raw extracted numbers, normalised units, and human review status.
    """
    __tablename__ = "activity_records"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reporting_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("evidence_files.id", ondelete="SET NULL"), nullable=True, index=True
    )
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("extraction_jobs.id", ondelete="SET NULL"), nullable=True
    )
    evidence_reference: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )  # e.g. "page 2, invoice table" or "cell C14" or "01:23 timestamp"
    evidence_type: Mapped[str] = mapped_column(String(50), nullable=False)  # electricity | diesel | supplier

    # Raw extracted values (immutable record of original AI output)
    raw_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    raw_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    raw_date_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    raw_date_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)

    # Normalised values (computed by deterministic registry, e.g. kWh, litres)
    normalised_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    normalised_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    status: Mapped[str] = mapped_column(
        String(50), default=ActivityRecordStatus.PENDING.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    file: Mapped[Optional["EvidenceFile"]] = relationship("EvidenceFile", back_populates="activity_records")
    revisions: Mapped[List["ActivityRevision"]] = relationship(
        "ActivityRevision", back_populates="activity_record", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_activity_records_period_status", "org_id", "period_id", "status"),
    )


class ActivityRevision(Base):
    """
    Audit trail for human corrections.
    Rather than overwriting raw activity data, each manual edit creates an immutable revision.
    """
    __tablename__ = "activity_revisions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("activity_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    previous_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    new_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    new_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    activity_record: Mapped["ActivityRecord"] = relationship("ActivityRecord", back_populates="revisions")
