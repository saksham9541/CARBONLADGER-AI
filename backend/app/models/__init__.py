"""
CarbonLedger AI — ORM Models Registry
======================================
Exposes all models for Alembic migrations and database operations.
"""

from app.core.database import Base
from app.models.enums import (
    ActivityRecordStatus,
    ApprovalDecision,
    ConsolidationApproach,
    EvidenceFileType,
    ExceptionFlagType,
    ExceptionStatus,
    ExtractionJobStatus,
    FactorVersionStatus,
    MembershipStatus,
    ReportingPeriodStatus,
    ReportStatus,
    ReportType,
    UserRole,
    WorksheetStatus,
)
from app.models.organization import (
    Facility,
    Organization,
    OrganizationMembership,
    ReportingBoundary,
    UserProfile,
)
from app.models.reporting_period import ReportingPeriod
from app.models.evidence import (
    ActivityRecord,
    ActivityRevision,
    EvidenceFile,
    ExtractionJob,
)
from app.models.factor import (
    EmissionFactor,
    FactorApproval,
    FactorVersion,
)
from app.models.calculation import (
    Calculation,
    EvidenceException,
    WorksheetVersion,
)
from app.models.report import (
    Report,
    ReportApproval,
)
from app.models.audit import AuditEvent

__all__ = [
    "Base",
    # Enums
    "UserRole",
    "MembershipStatus",
    "ReportingPeriodStatus",
    "ConsolidationApproach",
    "EvidenceFileType",
    "ExtractionJobStatus",
    "ActivityRecordStatus",
    "FactorVersionStatus",
    "WorksheetStatus",
    "ExceptionFlagType",
    "ExceptionStatus",
    "ReportType",
    "ReportStatus",
    "ApprovalDecision",
    # Models
    "Organization",
    "UserProfile",
    "OrganizationMembership",
    "Facility",
    "ReportingBoundary",
    "ReportingPeriod",
    "EvidenceFile",
    "ExtractionJob",
    "ActivityRecord",
    "ActivityRevision",
    "FactorVersion",
    "EmissionFactor",
    "FactorApproval",
    "Calculation",
    "WorksheetVersion",
    "EvidenceException",
    "Report",
    "ReportApproval",
    "AuditEvent",
]
