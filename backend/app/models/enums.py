"""
CarbonLedger AI — Database & Domain Status Enums
=================================================
Type-safe enums for database columns and API schemas.
"""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    AUDITOR = "auditor"


class MembershipStatus(str, enum.Enum):
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"


class ReportingPeriodStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    LOCKED = "locked"


class ConsolidationApproach(str, enum.Enum):
    OPERATIONAL_CONTROL = "operational_control"
    FINANCIAL_CONTROL = "financial_control"
    EQUITY_SHARE = "equity_share"


class EvidenceFileType(str, enum.Enum):
    PDF = "pdf"
    IMAGE = "image"
    EXCEL = "excel"
    AUDIO = "audio"
    CSV = "csv"


class ExtractionJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ActivityRecordStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    MISSING_EVIDENCE = "missing_evidence"


class FactorVersionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class WorksheetStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    ARCHIVED = "archived"


class ExceptionFlagType(str, enum.Enum):
    MISSING_EVIDENCE = "missing_evidence"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    UNKNOWN_UNIT = "unknown_unit"
    MISSING_FACTOR = "missing_factor"
    LOW_CONFIDENCE = "low_confidence"
    UNSUPPORTED_DECLARATION = "unsupported_declaration"


class ExceptionStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    WAIVED = "waived"


class ReportType(str, enum.Enum):
    FULL_INVENTORY = "full_inventory"
    EXECUTIVE_SUMMARY = "executive_summary"
    AUDITOR_PACKAGE = "auditor_package"


class ReportStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    PUBLISHED = "published"


class ApprovalDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
