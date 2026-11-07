"""
CarbonLedger AI — Health Endpoint Tests
========================================
Uses FastAPI's dependency_overrides to inject a SQLite in-memory session
so tests run without a live PostgreSQL instance (CI-safe).

Run with:  pytest tests/ -v
"""

from __future__ import annotations

import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set env vars BEFORE any app module is imported
os.environ["DATABASE_URL"] = "sqlite:///./test_carbonledger.db"
os.environ["SECRET_KEY"] = "ci-test-secret-not-for-production"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"

from app.core.config import get_settings
get_settings.cache_clear()

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from main import app

# ── SQLite test engine ────────────────────────────────────────
_TEST_DB = "sqlite:///./test_carbonledger.db"
_test_engine = create_engine(_TEST_DB, connect_args={"check_same_thread": False})
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    """Create tables before tests; drop + remove file after."""
    Base.metadata.create_all(bind=_test_engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_test_engine)
    _test_engine.dispose()
    if os.path.exists("./test_carbonledger.db"):
        try:
            os.remove("./test_carbonledger.db")
        except Exception:
            pass


# ── Tests ─────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_returns_200(self):
        """Health endpoint must return HTTP 200."""
        r = client.get("/api/health")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_response_has_required_fields(self):
        """Response body must contain all required fields."""
        r = client.get("/api/health")
        body = r.json()
        for field in ("status", "version", "timestamp", "environment", "services"):
            assert field in body, f"Missing field: '{field}'"

    def test_status_is_valid_enum_value(self):
        """Status must be one of the recognised enum values."""
        r = client.get("/api/health")
        assert r.json()["status"] in {"ok", "degraded", "error", "unconfigured"}

    def test_all_expected_services_present(self):
        """database, storage, and gemini keys must appear in services."""
        r = client.get("/api/health")
        services = r.json()["services"]
        for svc in ("database", "storage", "gemini"):
            assert svc in services, f"Service '{svc}' missing from response"

    def test_database_service_is_ok(self):
        """With SQLite available the database service must be ok."""
        r = client.get("/api/health")
        assert r.json()["services"]["database"] == "ok"

    def test_unconfigured_external_services(self):
        """Storage and gemini must be unconfigured when env vars are blank."""
        r = client.get("/api/health")
        services = r.json()["services"]
        assert services["storage"] in {"ok", "unconfigured"}
        assert services["gemini"] in {"ok", "unconfigured"}

    def test_environment_matches_env_var(self):
        """Environment field must reflect the ENVIRONMENT env var."""
        r = client.get("/api/health")
        assert r.json()["environment"] == "test"

    def test_version_is_semver(self):
        """Version field must look like x.y.z."""
        r = client.get("/api/health")
        version = r.json()["version"]
        parts = version.split(".")
        assert len(parts) == 3, f"Version '{version}' is not semver"
        assert all(p.isdigit() for p in parts)


class TestSystemRoutes:
    def test_docs_available_in_test_env(self):
        """Swagger UI must be accessible outside production."""
        r = client.get("/docs")
        assert r.status_code == 200

    def test_unknown_route_is_404(self):
        """Undefined routes must return 404, not 500."""
        r = client.get("/api/this-does-not-exist-xyz")
        assert r.status_code == 404
