"""
CarbonLedger AI — Supabase Auth & Organization RBAC
====================================================
Server-side JWT verification against Supabase Auth (JWKS/RS256 or HS256 secret)
and strict organization role-based access control (RBAC).

NEVER trusts client-supplied roles. All role checks query the database
organization_memberships table with deny-by-default isolation.
"""

import time
import uuid
from uuid import UUID
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwk, jwt
from jose.exceptions import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.enums import MembershipStatus, UserRole
from app.models.organization import Organization, OrganizationMembership, UserProfile

logger = get_logger(__name__)
settings = get_settings()

security = HTTPBearer(auto_error=False)


# ── JWKS In-Memory Cache ──────────────────────────────────────
class JWKSCache:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self.cached_keys: Dict[str, Any] = {}
        self.last_fetched: float = 0.0

    def get_key(self, kid: Optional[str], jwks_url: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        if not self.cached_keys or (now - self.last_fetched > self.ttl_seconds):
            self.refresh(jwks_url)

        if not kid and self.cached_keys:
            # If token has no kid, return the first available key
            return next(iter(self.cached_keys.values()))
        return self.cached_keys.get(kid) if kid else None

    def refresh(self, jwks_url: str) -> None:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(jwks_url)
                if resp.status_code == 200:
                    data = resp.json()
                    keys = data.get("keys", [])
                    self.cached_keys = {k.get("kid", str(i)): k for i, k in enumerate(keys)}
                    self.last_fetched = time.time()
                    logger.info("JWKS refreshed", keys_count=len(self.cached_keys))
        except Exception as exc:
            logger.warning("Failed to refresh JWKS from Supabase", error=str(exc))

    def set_mock_keys(self, keys: Dict[str, Any]) -> None:
        """Testing hook to inject mock keys without network calls."""
        self.cached_keys = keys
        self.last_fetched = time.time()


jwks_cache = JWKSCache()


# ── JWT Verification ──────────────────────────────────────────
def verify_supabase_jwt(token: str) -> Dict[str, Any]:
    """
    Verify Supabase JWT server-side.
    Validates algorithm, signature, issuer (if configured), and audience.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token header format",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    alg = unverified_header.get("alg", "HS256")
    kid = unverified_header.get("kid")

    options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_aud": bool(settings.supabase_jwt_audience),
    }

    try:
        if alg in ("RS256", "ES256"):
            # Asymmetric verification via JWKS
            jwks_url = settings.supabase_jwks_url
            if not jwks_url and settings.supabase_url:
                jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

            if not jwks_url and not jwks_cache.cached_keys:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Server configuration error: Supabase JWKS URL not configured",
                )

            key_dict = jwks_cache.get_key(kid, jwks_url) if jwks_url else None
            if not key_dict:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Matching public key not found in JWKS",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            public_key = jwk.construct(key_dict)
            payload = jwt.decode(
                token,
                public_key.to_pem().decode("utf-8") if hasattr(public_key, "to_pem") else public_key,
                algorithms=[alg],
                audience=settings.supabase_jwt_audience or None,
                issuer=settings.supabase_jwt_issuer or None,
                options=options,
            )
        else:
            # Symmetric verification via secret
            secret = settings.supabase_jwt_secret or settings.secret_key
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=settings.supabase_jwt_audience or None,
                issuer=settings.supabase_jwt_issuer or None,
                options=options,
            )

        if "sub" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing required 'sub' claim",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Current Authenticated User Dependency ─────────────────────
def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: Session = Depends(get_db),
) -> UserProfile:
    """
    FastAPI dependency: Extracts and verifies JWT bearer token,
    and returns the corresponding UserProfile.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_supabase_jwt(credentials.credentials)

    try:
        user_uuid = uuid.UUID(payload["sub"])
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed user ID claim in token",
        )

    # Email from standard claim or Supabase user_metadata
    email = payload.get("email") or payload.get("user_metadata", {}).get("email")
    if not email:
        email = f"user_{str(user_uuid)[:8]}@carbonledger.local"

    full_name = payload.get("user_metadata", {}).get("full_name")

    # Fetch user or synchronize profile on demand
    user = db.execute(select(UserProfile).where(UserProfile.id == user_uuid)).scalar_one_or_none()
    if not user:
        user = UserProfile(
            id=user_uuid,
            email=email,
            full_name=full_name,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Synchronized user profile from token", user_id=str(user_uuid), email=email)
    elif not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    return user


# ── Organization Role-Based Access Control (RBAC) ──────────────
class RequireOrgRole:
    """
    Dependency that enforces:
    1. Organization exists.
    2. Current user has an ACTIVE membership in this organization.
    3. Member's role matches one of the allowed roles (admin, analyst, auditor).

    NEVER relies on roles passed by the client.
    """

    def __init__(self, allowed_roles: List[UserRole]) -> None:
        self.allowed_roles = [r.value for r in allowed_roles]

    def __call__(
        self,
        org_id: UUID,
        current_user: UserProfile = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> OrganizationMembership:
        # Verify organization exists
        org = db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Organization '{org_id}' not found",
            )

        # Lookup membership in database
        membership = db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.org_id == org_id,
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.status == MembershipStatus.ACTIVE.value,
            )
        ).scalar_one_or_none()

        if not membership:
            logger.warning(
                "Access denied: User is not an active member of organization",
                user_id=str(current_user.id),
                org_id=str(org_id),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not an active member of this organization",
            )

        if membership.role not in self.allowed_roles:
            logger.warning(
                "Access denied: Insufficient role",
                user_id=str(current_user.id),
                org_id=str(org_id),
                user_role=membership.role,
                allowed_roles=self.allowed_roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Operation requires one of roles: {', '.join(self.allowed_roles)}",
            )

        return membership


# Convenience dependencies
require_admin = RequireOrgRole([UserRole.ADMIN])
require_analyst_or_admin = RequireOrgRole([UserRole.ADMIN, UserRole.ANALYST])
require_any_member = RequireOrgRole([UserRole.ADMIN, UserRole.ANALYST, UserRole.AUDITOR])
