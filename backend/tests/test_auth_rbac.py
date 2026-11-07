"""
CarbonLedger AI — Supabase Auth & RBAC Security Tests
======================================================
Proves:
1. Strict tenant isolation (users cannot read or modify another organization's data).
2. Role enforcement (admin vs analyst vs auditor).
3. Client-supplied role claims in JWT or payload are completely ignored.
4. Unauthenticated or invalid token requests are rejected with 401.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import date

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set environment variables for testing
TEST_SECRET = "super-secret-test-key-32-chars-long!!"
os.environ["DATABASE_URL"] = "sqlite:///./test_rbac.db"
os.environ["SECRET_KEY"] = TEST_SECRET
os.environ["SUPABASE_JWT_SECRET"] = TEST_SECRET
os.environ["SUPABASE_JWT_AUDIENCE"] = "authenticated"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"

from app.core.config import get_settings
get_settings.cache_clear()

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.models.enums import MembershipStatus, UserRole
from app.models.organization import Organization, OrganizationMembership, UserProfile
from app.models.reporting_period import ReportingPeriod
from main import app

# ── SQLite Test Engine & DB Session Override ──────────────────
_TEST_DB = "sqlite:///./test_rbac.db"
_engine = create_engine(_TEST_DB, connect_args={"check_same_thread": False})
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


# ── JWT Helper ────────────────────────────────────────────────
def create_test_jwt(
    user_id: uuid.UUID,
    email: str,
    extra_claims: dict = None,
    expires_in: int = 3600,
    secret: str = TEST_SECRET,
) -> str:
    """Creates a signed Supabase-format JWT."""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "iat": now,
        "exp": now + expires_in,
        "role": "authenticated",
        **(extra_claims or {}),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures: Multi-Tenant Setup ──────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def setup_rbac_database():
    Base.metadata.create_all(bind=_engine)
    app.dependency_overrides[get_db] = _override_get_db
    db = _TestSession()

    try:
        # Create Organizations
        org1 = Organization(
            id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            name="Green Manufacturing Ltd",
            slug="green-mfg",
            country="IN",
        )
        org2 = Organization(
            id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            name="Acme Cement Corp",
            slug="acme-cement",
            country="IN",
        )
        db.add_all([org1, org2])

        # Create Users
        # Org 1 Admin
        user_admin = UserProfile(
            id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            email="admin@greenmfg.com",
            full_name="Alice Admin",
            is_active=True,
        )
        # Org 1 Analyst
        user_analyst = UserProfile(
            id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            email="analyst@greenmfg.com",
            full_name="Bob Analyst",
            is_active=True,
        )
        # Org 1 Auditor
        user_auditor = UserProfile(
            id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            email="auditor@greenmfg.com",
            full_name="Charlie Auditor",
            is_active=True,
        )
        # Org 2 Member (Outsider to Org 1)
        user_outsider = UserProfile(
            id=uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
            email="manager@acmecement.com",
            full_name="David Outsider",
            is_active=True,
        )
        db.add_all([user_admin, user_analyst, user_auditor, user_outsider])

        # Assign Memberships in Database
        mem_admin = OrganizationMembership(
            org_id=org1.id,
            user_id=user_admin.id,
            role=UserRole.ADMIN.value,
            status=MembershipStatus.ACTIVE.value,
        )
        mem_analyst = OrganizationMembership(
            org_id=org1.id,
            user_id=user_analyst.id,
            role=UserRole.ANALYST.value,
            status=MembershipStatus.ACTIVE.value,
        )
        mem_auditor = OrganizationMembership(
            org_id=org1.id,
            user_id=user_auditor.id,
            role=UserRole.AUDITOR.value,
            status=MembershipStatus.ACTIVE.value,
        )
        mem_outsider = OrganizationMembership(
            org_id=org2.id,
            user_id=user_outsider.id,
            role=UserRole.ADMIN.value,
            status=MembershipStatus.ACTIVE.value,
        )
        db.add_all([mem_admin, mem_analyst, mem_auditor, mem_outsider])

        # Create initial Reporting Period in Org 1
        period1 = ReportingPeriod(
            id=uuid.UUID("99999999-9999-9999-9999-999999999999"),
            org_id=org1.id,
            name="CY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="draft",
        )
        db.add(period1)

        db.commit()
    finally:
        db.close()

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_engine)
    _engine.dispose()
    if os.path.exists("./test_rbac.db"):
        try:
            os.remove("./test_rbac.db")
        except Exception:
            pass


# ── Tokens ────────────────────────────────────────────────────
@pytest.fixture
def token_admin():
    return create_test_jwt(uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), "admin@greenmfg.com")


@pytest.fixture
def token_analyst():
    return create_test_jwt(uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"), "analyst@greenmfg.com")


@pytest.fixture
def token_auditor():
    return create_test_jwt(uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"), "auditor@greenmfg.com")


@pytest.fixture
def token_outsider():
    return create_test_jwt(uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"), "manager@acmecement.com")


ORG1_ID = "11111111-1111-1111-1111-111111111111"
ORG2_ID = "22222222-2222-2222-2222-222222222222"
PERIOD1_ID = "99999999-9999-9999-9999-999999999999"


# ── Test Suite 1: Authentication Boundary ─────────────────────
class TestAuthenticationSecurity:
    def test_missing_auth_header_rejected(self):
        """Unauthenticated requests must be rejected with 401."""
        res = client.get(f"/api/organizations/{ORG1_ID}")
        assert res.status_code == 401
        assert "Authorization header" in res.json()["detail"]

    def test_expired_token_rejected(self):
        """Expired JWTs must be rejected with 401."""
        expired_token = create_test_jwt(
            uuid.uuid4(), "test@expired.com", expires_in=-100
        )
        res = client.get(f"/api/organizations/{ORG1_ID}", headers=auth_header(expired_token))
        assert res.status_code == 401
        assert "expired" in res.json()["detail"].lower()

    def test_invalid_signature_rejected(self):
        """JWT with forged signature must be rejected with 401."""
        forged_token = create_test_jwt(
            uuid.uuid4(), "attacker@forged.com", secret="wrong-secret-key-attacker-guess!"
        )
        res = client.get(f"/api/organizations/{ORG1_ID}", headers=auth_header(forged_token))
        assert res.status_code == 401


# ── Test Suite 2: Strict Tenant Isolation ─────────────────────
class TestTenantIsolation:
    def test_outsider_cannot_read_organization_details(self, token_outsider):
        """User from Org 2 cannot read Org 1 details (403 Forbidden)."""
        res = client.get(f"/api/organizations/{ORG1_ID}", headers=auth_header(token_outsider))
        assert res.status_code == 403
        assert "not an active member" in res.json()["detail"]

    def test_outsider_cannot_list_organization_members(self, token_outsider):
        """User from Org 2 cannot view Org 1 membership roster (403 Forbidden)."""
        res = client.get(f"/api/organizations/{ORG1_ID}/members", headers=auth_header(token_outsider))
        assert res.status_code == 403

    def test_outsider_cannot_add_members_to_organization(self, token_outsider):
        """User from Org 2 cannot add members to Org 1 (403 Forbidden)."""
        payload = {"email": "injected@outsider.com", "role": "admin"}
        res = client.post(
            f"/api/organizations/{ORG1_ID}/members",
            json=payload,
            headers=auth_header(token_outsider),
        )
        assert res.status_code == 403

    def test_outsider_cannot_list_reporting_periods(self, token_outsider):
        """User from Org 2 cannot view Org 1 reporting periods (403 Forbidden)."""
        res = client.get(
            f"/api/organizations/{ORG1_ID}/reporting-periods",
            headers=auth_header(token_outsider),
        )
        assert res.status_code == 403

    def test_outsider_cannot_create_reporting_period(self, token_outsider):
        """User from Org 2 cannot create reporting period in Org 1 (403 Forbidden)."""
        payload = {"name": "Hacked Period", "start_date": "2026-01-01", "end_date": "2026-03-31"}
        res = client.post(
            f"/api/organizations/{ORG1_ID}/reporting-periods",
            json=payload,
            headers=auth_header(token_outsider),
        )
        assert res.status_code == 403

    def test_outsider_cannot_read_specific_reporting_period(self, token_outsider):
        """User from Org 2 cannot access Org 1's specific reporting period (403 Forbidden)."""
        res = client.get(
            f"/api/organizations/{ORG1_ID}/reporting-periods/{PERIOD1_ID}",
            headers=auth_header(token_outsider),
        )
        assert res.status_code == 403

    def test_outsider_cannot_update_reporting_period(self, token_outsider):
        """User from Org 2 cannot modify Org 1's reporting period (403 Forbidden)."""
        payload = {"name": "Tampered Period"}
        res = client.patch(
            f"/api/organizations/{ORG1_ID}/reporting-periods/{PERIOD1_ID}",
            json=payload,
            headers=auth_header(token_outsider),
        )
        assert res.status_code == 403


# ── Test Suite 3: Role-Based Access Control (RBAC) ────────────
class TestRolePermissions:
    def test_auditor_can_read_periods(self, token_auditor):
        """Auditor has read access to reporting periods."""
        res = client.get(
            f"/api/organizations/{ORG1_ID}/reporting-periods",
            headers=auth_header(token_auditor),
        )
        assert res.status_code == 200
        periods = res.json()
        assert len(periods) >= 1
        assert periods[0]["id"] == PERIOD1_ID

    def test_auditor_cannot_create_reporting_period(self, token_auditor):
        """Auditor is read-only; attempts to create period are rejected with 403."""
        payload = {"name": "Auditor Created Period", "start_date": "2026-04-01", "end_date": "2026-06-30"}
        res = client.post(
            f"/api/organizations/{ORG1_ID}/reporting-periods",
            json=payload,
            headers=auth_header(token_auditor),
        )
        assert res.status_code == 403
        assert "requires one of roles" in res.json()["detail"]

    def test_auditor_cannot_modify_reporting_period(self, token_auditor):
        """Auditor cannot update reporting periods."""
        payload = {"name": "Auditor Modified Name"}
        res = client.patch(
            f"/api/organizations/{ORG1_ID}/reporting-periods/{PERIOD1_ID}",
            json=payload,
            headers=auth_header(token_auditor),
        )
        assert res.status_code == 403

    def test_analyst_can_create_reporting_period(self, token_analyst):
        """Analyst has permission to create reporting periods."""
        payload = {"name": "FY 2026-27 Q1", "start_date": "2026-04-01", "end_date": "2026-06-30"}
        res = client.post(
            f"/api/organizations/{ORG1_ID}/reporting-periods",
            json=payload,
            headers=auth_header(token_analyst),
        )
        assert res.status_code == 201
        assert res.json()["name"] == "FY 2026-27 Q1"

    def test_analyst_can_update_reporting_period(self, token_analyst):
        """Analyst has permission to update reporting periods."""
        payload = {"status": "in_progress"}
        res = client.patch(
            f"/api/organizations/{ORG1_ID}/reporting-periods/{PERIOD1_ID}",
            json=payload,
            headers=auth_header(token_analyst),
        )
        assert res.status_code == 200
        assert res.json()["status"] == "in_progress"

    def test_analyst_cannot_add_members(self, token_analyst):
        """Analyst cannot add members (membership management is Admin-only)."""
        payload = {"email": "newbie@greenmfg.com", "role": "analyst"}
        res = client.post(
            f"/api/organizations/{ORG1_ID}/members",
            json=payload,
            headers=auth_header(token_analyst),
        )
        assert res.status_code == 403
        assert "admin" in res.json()["detail"].lower()

    def test_admin_can_add_members(self, token_admin):
        """Admin can add or invite members to organization."""
        payload = {"email": "sam.analyst@greenmfg.com", "role": "analyst"}
        res = client.post(
            f"/api/organizations/{ORG1_ID}/members",
            json=payload,
            headers=auth_header(token_admin),
        )
        assert res.status_code == 201
        assert res.json()["email"] == "sam.analyst@greenmfg.com"
        assert res.json()["role"] == "analyst"


# ── Test Suite 4: Client-Supplied Role Ignored ─────────────────
class TestClientSuppliedRoleIgnored:
    def test_client_role_claim_in_token_ignored(self):
        """
        An attacker with Auditor role in the DB injects `user_metadata: {"role": "admin"}`
        into their token. The server MUST look up the role in the database and deny write access.
        """
        auditor_uuid = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
        forged_claims = {
            "role": "admin",
            "user_metadata": {"role": "admin"},
            "app_metadata": {"role": "admin"},
        }
        forged_token = create_test_jwt(auditor_uuid, "auditor@greenmfg.com", extra_claims=forged_claims)

        # Attempt an admin-only operation (adding member)
        payload = {"email": "escalated@greenmfg.com", "role": "admin"}
        res = client.post(
            f"/api/organizations/{ORG1_ID}/members",
            json=payload,
            headers=auth_header(forged_token),
        )
        # MUST BE DENIED because database has role="auditor"
        assert res.status_code == 403
        assert "admin" in res.json()["detail"].lower()


# ── Test Suite 5: Organization Scoping ────────────────────────
class TestOrganizationScoping:
    def test_list_my_organizations_only_returns_memberships(self, token_admin, token_outsider):
        """Users only see organizations they belong to."""
        res_admin = client.get("/api/organizations", headers=auth_header(token_admin))
        assert res_admin.status_code == 200
        org_ids_admin = [o["id"] for o in res_admin.json()]
        assert ORG1_ID in org_ids_admin
        assert ORG2_ID not in org_ids_admin

        res_outsider = client.get("/api/organizations", headers=auth_header(token_outsider))
        assert res_outsider.status_code == 200
        org_ids_outsider = [o["id"] for o in res_outsider.json()]
        assert ORG2_ID in org_ids_outsider
        assert ORG1_ID not in org_ids_outsider
