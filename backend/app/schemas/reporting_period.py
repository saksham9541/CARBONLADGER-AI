"""
CarbonLedger AI — Reporting Period Schemas
==========================================
Pydantic schemas for reporting period creation, updates, and responses.
"""

from __future__ import annotations

import uuid
from uuid import UUID
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ReportingPeriodStatus


class ReportingPeriodCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Period title, e.g. CY 2026")
    start_date: date = Field(..., description="Start of reporting interval")
    end_date: date = Field(..., description="End of reporting interval")
    boundary_id: Optional[UUID] = Field(None, description="Optional reporting boundary ID")

    @model_validator(mode="after")
    def validate_date_order(self) -> "ReportingPeriodCreate":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be before or equal to end_date")
        return self


class ReportingPeriodUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[ReportingPeriodStatus] = None


class ReportingPeriodResponse(BaseModel):
    id: UUID
    org_id: UUID
    boundary_id: Optional[UUID]
    name: str
    start_date: date
    end_date: date
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
