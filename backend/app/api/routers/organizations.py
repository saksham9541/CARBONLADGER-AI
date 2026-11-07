"""
CarbonLedger AI — Organizations & Memberships Router
====================================================
Tenant lifecycle management with strict organization isolation.
"""

import uuid
from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin, require_any_member
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.enums import MembershipStatus, UserRole
from app.models.organization import Organization, OrganizationMembership, UserProfile
from app.schemas.organization import (
    MemberAdd,
    MemberResponse,
    OrganizationCreate,
    OrganizationResponse,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])
logger = get_logger(__name__)


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization",
    description="Creates an organization and automatically provisions the creator as an Admin member.",
)
def create_organization(
    payload: OrganizationCreate,
    current_user: UserProfile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    # Check slug uniqueness
    existing = db.execute(
        select(Organization).where(Organization.slug == payload.slug)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An organization with slug '{payload.slug}' already exists",
        )

    org = Organization(
        name=payload.name,
        slug=payload.slug,
        country=payload.country.upper(),
    )
    db.add(org)
    db.flush()

    # Add creator as Admin
    membership = OrganizationMembership(
        org_id=org.id,
        user_id=current_user.id,
        role=UserRole.ADMIN.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db.add(membership)
    db.commit()
    db.refresh(org)

    logger.info(
        "Organization created",
        org_id=str(org.id),
        name=org.name,
        creator_id=str(current_user.id),
    )
    return OrganizationResponse.model_validate(org)


@router.get(
    "",
    response_model=List[OrganizationResponse],
    summary="List caller's organizations",
    description="Returns all organizations where the authenticated user is an active member.",
)
def list_my_organizations(
    current_user: UserProfile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[OrganizationResponse]:
    query = (
        select(Organization)
        .join(OrganizationMembership, OrganizationMembership.org_id == Organization.id)
        .where(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.status == MembershipStatus.ACTIVE.value,
        )
        .order_by(Organization.name)
    )
    orgs = db.execute(query).scalars().all()
    return [OrganizationResponse.model_validate(o) for o in orgs]


@router.get(
    "/{org_id}",
    response_model=OrganizationResponse,
    summary="Get organization details",
    description="Requires active membership in the organization.",
)
def get_organization(
    org_id: UUID,
    _membership: OrganizationMembership = Depends(require_any_member),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    org = db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrganizationResponse.model_validate(org)


@router.post(
    "/{org_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add or invite organization member",
    description="Requires Admin role in the organization. Client cannot self-grant roles.",
)
def add_member(
    org_id: UUID,
    payload: MemberAdd,
    _admin_membership: OrganizationMembership = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MemberResponse:
    # Resolve or create UserProfile by email
    target_user = None
    if payload.user_id:
        target_user = db.execute(
            select(UserProfile).where(UserProfile.id == payload.user_id)
        ).scalar_one_or_none()

    if not target_user:
        target_user = db.execute(
            select(UserProfile).where(UserProfile.email == payload.email)
        ).scalar_one_or_none()

    if not target_user:
        target_user = UserProfile(
            id=payload.user_id or uuid.uuid4(),
            email=payload.email,
            is_active=True,
        )
        db.add(target_user)
        db.flush()

    # Check for existing membership
    existing_mem = db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.org_id == org_id,
            OrganizationMembership.user_id == target_user.id,
        )
    ).scalar_one_or_none()

    if existing_mem:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this organization",
        )

    new_mem = OrganizationMembership(
        org_id=org_id,
        user_id=target_user.id,
        role=payload.role.value,
        status=MembershipStatus.ACTIVE.value,
    )
    db.add(new_mem)
    db.commit()
    db.refresh(new_mem)

    return MemberResponse(
        id=new_mem.id,
        org_id=new_mem.org_id,
        user_id=new_mem.user_id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=new_mem.role,
        status=new_mem.status,
        created_at=new_mem.created_at,
    )


@router.get(
    "/{org_id}/members",
    response_model=List[MemberResponse],
    summary="List organization members",
    description="Requires active membership in the organization.",
)
def list_members(
    org_id: UUID,
    _membership: OrganizationMembership = Depends(require_any_member),
    db: Session = Depends(get_db),
) -> List[MemberResponse]:
    query = (
        select(OrganizationMembership, UserProfile)
        .join(UserProfile, UserProfile.id == OrganizationMembership.user_id)
        .where(OrganizationMembership.org_id == org_id)
        .order_by(OrganizationMembership.created_at)
    )
    results = db.execute(query).all()

    return [
        MemberResponse(
            id=mem.id,
            org_id=mem.org_id,
            user_id=mem.user_id,
            email=usr.email,
            full_name=usr.full_name,
            role=mem.role,
            status=mem.status,
            created_at=mem.created_at,
        )
        for mem, usr in results
    ]
