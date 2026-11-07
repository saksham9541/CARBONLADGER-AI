"""
CarbonLedger AI — Organization & Membership Schemas
===================================================
Pydantic models for organization lifecycle and membership management.
"""

from __future__ import annotations

import uuid
from uuid import UUID
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MembershipStatus, UserRole


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Legal company name")
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$", description="URL-friendly unique slug")
    country: str = Field(default="IN", min_length=2, max_length=2, description="ISO-3166-1 alpha-2 country code")


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    country: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MemberAdd(BaseModel):
    user_id: Optional[UUID] = Field(None, description="Existing user UUID")
    email: str = Field(..., description="User email to invite or associate")
    role: UserRole = Field(default=UserRole.ANALYST, description="Role within the organization")


class MemberUpdate(BaseModel):
    role: Optional[UserRole] = None
    status: Optional[MembershipStatus] = None


class MemberResponse(BaseModel):
    id: UUID
    org_id: UUID
    user_id: UUID
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
