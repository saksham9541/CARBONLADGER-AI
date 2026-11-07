"""
CarbonLedger AI — Evidence & Extraction Schemas
===============================================
Pydantic v2 schemas for evidence files, extraction jobs, and upload responses.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EvidenceFileType, ExtractionJobStatus


class ActivityRecordResponse(BaseModel):
    id: UUID
    org_id: UUID
    period_id: UUID
    file_id: Optional[UUID] = None
    facility_id: Optional[UUID] = None
    job_id: Optional[UUID] = None
    evidence_reference: Optional[str] = None
    evidence_type: str
    raw_value: Optional[Decimal] = None
    raw_unit: Optional[str] = None
    raw_date_start: Optional[date] = None
    raw_date_end: Optional[date] = None
    confidence: Optional[Decimal] = None
    normalised_value: Optional[Decimal] = None
    normalised_unit: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ExtractionJobResponse(BaseModel):
    id: UUID
    org_id: UUID
    file_id: UUID
    status: str
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class EvidenceFileResponse(BaseModel):
    id: UUID
    org_id: UUID
    period_id: Optional[UUID] = None
    facility_id: Optional[UUID] = None
    original_name: str
    storage_path: str
    file_hash: str
    file_type: str
    mime_type: str
    size_bytes: int
    uploaded_by: Optional[UUID] = None
    uploaded_at: datetime
    is_deleted: bool
    latest_job_status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class EvidenceDetailResponse(BaseModel):
    file: EvidenceFileResponse
    latest_job: Optional[ExtractionJobResponse] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class EvidenceFileListResponse(BaseModel):
    items: List[EvidenceFileResponse]
    total: int
