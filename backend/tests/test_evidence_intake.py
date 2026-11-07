"""
CarbonLedger AI — Phase 3 Multimodal Evidence Intake Integration Tests
======================================================================
Tests:
1. Text-based PDF electricity bill upload & PyMuPDF extraction (scanned_pages=False).
2. Scanned PDF electricity bill upload & scanned page detection (scanned_pages=True).
3. Photographed invoice JPG upload & Pillow EXIF orientation preprocessing.
4. Photographed invoice PNG upload & dimensions validation.
5. XLSX supplier declaration upload & openpyxl coordinate/unit parsing.
6. CSV supplier declaration upload & delimiter/unit parsing.
7. Audio voice note WAV upload & container/timestamped segment parsing.
8. Audio voice note MP3 upload & transcription adapter parsing.
9. Secure download (attachment disposition) and preview (inline disposition) endpoints.
10. Reprocessing endpoint.
11. Soft-delete endpoint.
12. Strict multi-tenant isolation (Tenant B cannot read/download Tenant A files).
13. Role-based access control (Auditor read-only; Analyst/Admin upload and delete).
14. Security validations (Unsupported types rejected with 415, spoofed files rejected with 400, unauthenticated rejected with 401).
"""

from __future__ import annotations

import hashlib
import io
import os
import sys
import time
import uuid
from typing import Generator

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configure test environment
TEST_SECRET = "super-secret-test-key-32-chars-long!!"
os.environ["DATABASE_URL"] = "sqlite:///./test_evidence.db"
os.environ["SECRET_KEY"] = TEST_SECRET
os.environ["SUPABASE_JWT_SECRET"] = TEST_SECRET
os.environ["SUPABASE_JWT_AUDIENCE"] = "authenticated"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"
os.environ["LOCAL_STORAGE_PATH"] = "./test_storage_evidence"

from app.core.config import get_settings
get_settings.cache_clear()

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, get_db
from app.models.enums import MembershipStatus, UserRole
from app.models.evidence import EvidenceFile, ExtractionJob
from app.models.organization import Organization, OrganizationMembership, UserProfile
from app.models.reporting_period import ReportingPeriod
from main import app
from tests.fixtures.synthetic_evidence import (
    generate_synthetic_invoice_jpg,
    generate_synthetic_invoice_png,
    generate_synthetic_mp3_audio,
    generate_synthetic_scanned_pdf,
    generate_synthetic_supplier_csv,
    generate_synthetic_supplier_xlsx,
    generate_synthetic_text_pdf,
    generate_synthetic_wav_audio,
)

# ── SQLite Test Engine & DB Session Override ──────────────────
_TEST_DB = "sqlite:///./test_evidence.db"
_engine = create_engine(_TEST_DB, connect_args={"check_same_thread": False})
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def create_test_jwt(
    user_id: uuid.UUID,
    email: str,
    extra_claims: dict = None,
    expires_in: int = 3600,
    secret: str = TEST_SECRET,
) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "iss": "supabase-test",
        "iat": now,
        "exp": now + expires_in,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, secret, algorithm="HS256")


# Fixed IDs for determinism
ORG_1_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ORG_2_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

ADMIN_1_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ANALYST_1_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
AUDITOR_1_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
OUTSIDER_2_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture(autouse=True)
def setup_test_db():
    """Build fresh test database and seed test organizations & memberships."""
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)

    db: Session = _TestSession()
    try:
        # Seed Org 1
        org1 = Organization(id=ORG_1_ID, name="Tata Manufacturing", slug="tata-mfg", country="IN")
        # Seed Org 2
        org2 = Organization(id=ORG_2_ID, name="Reliance Textiles", slug="reliance-tex", country="IN")
        db.add_all([org1, org2])
        db.flush()

        # Seed Users
        u_admin = UserProfile(id=ADMIN_1_ID, email="admin@tata.com", full_name="Admin Tata")
        u_analyst = UserProfile(id=ANALYST_1_ID, email="analyst@tata.com", full_name="Analyst Tata")
        u_auditor = UserProfile(id=AUDITOR_1_ID, email="auditor@kpmg.com", full_name="Auditor KPMG")
        u_outsider = UserProfile(id=OUTSIDER_2_ID, email="user@reliance.com", full_name="Reliance User")
        db.add_all([u_admin, u_analyst, u_auditor, u_outsider])
        db.flush()

        # Memberships for Org 1
        m_admin = OrganizationMembership(
            id=uuid.uuid4(), org_id=ORG_1_ID, user_id=ADMIN_1_ID, role=UserRole.ADMIN, status=MembershipStatus.ACTIVE
        )
        m_analyst = OrganizationMembership(
            id=uuid.uuid4(), org_id=ORG_1_ID, user_id=ANALYST_1_ID, role=UserRole.ANALYST, status=MembershipStatus.ACTIVE
        )
        m_auditor = OrganizationMembership(
            id=uuid.uuid4(), org_id=ORG_1_ID, user_id=AUDITOR_1_ID, role=UserRole.AUDITOR, status=MembershipStatus.ACTIVE
        )

        # Memberships for Org 2
        m_outsider = OrganizationMembership(
            id=uuid.uuid4(), org_id=ORG_2_ID, user_id=OUTSIDER_2_ID, role=UserRole.ADMIN, status=MembershipStatus.ACTIVE
        )
        db.add_all([m_admin, m_analyst, m_auditor, m_outsider])
        db.commit()
    finally:
        db.close()

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_engine)


def auth_headers(user_id: uuid.UUID, email: str) -> dict:
    token = create_test_jwt(user_id=user_id, email=email)
    return {"Authorization": f"Bearer {token}"}


class TestMultimodalEvidenceUpload:
    """Tests intake processing for every evidence modality."""

    def test_text_pdf_upload_and_extraction(self):
        """Modality 1: Text-based PDF electricity bill."""
        pdf_bytes = generate_synthetic_text_pdf()
        expected_hash = hashlib.sha256(pdf_bytes).hexdigest()

        response = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("january_electricity_bill.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 201, response.text
        data = response.json()

        file_meta = data["file"]
        assert file_meta["original_name"] == "january_electricity_bill.pdf"
        assert file_meta["file_type"] == "pdf"
        assert file_meta["file_hash"] == expected_hash
        assert file_meta["size_bytes"] == len(pdf_bytes)

        job = data["latest_job"]
        assert job["status"] == "completed"
        extracted = job["extracted_data"]["data"]
        assert extracted["total_pages"] == 2
        assert extracted["has_scanned_pages"] is False
        assert "4,500 kWh" in extracted["full_text"]
        assert "TATA POWER" in extracted["full_text"]

    def test_scanned_pdf_upload_and_detection(self):
        """Modality 2: Scanned PDF bill (scanned page detection)."""
        scanned_bytes = generate_synthetic_scanned_pdf()

        response = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("scanned_meter_card.pdf", scanned_bytes, "application/pdf")},
        )
        assert response.status_code == 201
        data = response.json()
        job = data["latest_job"]
        assert job["status"] == "completed"

        extracted = job["extracted_data"]["data"]
        assert extracted["total_pages"] == 1
        assert extracted["has_scanned_pages"] is True
        assert extracted["is_entirely_scanned"] is True
        assert extracted["scanned_pages_count"] == 1

    def test_invoice_jpg_upload_and_orientation_preprocessing(self):
        """Modality 3: Photographed diesel invoice in JPG format."""
        jpg_bytes = generate_synthetic_invoice_jpg()

        response = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("diesel_fuel_invoice.jpg", jpg_bytes, "image/jpeg")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["file"]["file_type"] == "image"
        assert data["file"]["mime_type"] == "image/jpeg"

        job = data["latest_job"]
        assert job["status"] == "completed"
        img_data = job["extracted_data"]["data"]
        assert img_data["parser"] == "Pillow"
        assert img_data["orientation_corrected"] is True
        assert "normalized_dimensions" in img_data

    def test_invoice_png_upload(self):
        """Modality 4: Invoice in PNG format."""
        png_bytes = generate_synthetic_invoice_png()

        response = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ADMIN_1_ID, "admin@tata.com"),
            files={"file": ("delivery_challan.png", png_bytes, "image/png")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["file"]["file_type"] == "image"
        assert data["file"]["mime_type"] == "image/png"
        assert data["latest_job"]["status"] == "completed"

    def test_supplier_xlsx_upload_and_coordinate_parsing(self):
        """Modality 5: Supplier declaration in XLSX format."""
        xlsx_bytes = generate_synthetic_supplier_xlsx()

        response = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("supplier_declaration.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["file"]["file_type"] == "excel"

        job = data["latest_job"]
        assert job["status"] == "completed"
        sheet_data = job["extracted_data"]["data"]
        assert "Supplier Declarations" in sheet_data["sheet_names"]
        assert "Submeter Readings" in sheet_data["sheet_names"]
        # Units detected
        units = sheet_data["detected_units"]
        assert "litres" in units
        assert "kl" in units
        assert "kwh" in units

    def test_supplier_csv_upload_and_unit_detection(self):
        """Modality 6: Supplier declaration in CSV format."""
        csv_bytes = generate_synthetic_supplier_csv()

        response = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("activity_fuel_records.csv", csv_bytes, "text/csv")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["file"]["file_type"] == "csv"

        job = data["latest_job"]
        assert job["status"] == "completed"
        csv_data = job["extracted_data"]["data"]
        assert csv_data["delimiter"] == ","
        assert "litres" in csv_data["detected_units"]
        assert "m3" in csv_data["detected_units"]
        assert "kwh" in csv_data["detected_units"]

    def test_voice_note_wav_upload_and_transcription_adapter(self):
        """Modality 7: Audio voice note in WAV format."""
        wav_bytes = generate_synthetic_wav_audio()

        response = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("missing_month_voice_note.wav", wav_bytes, "audio/wav")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["file"]["file_type"] == "audio"
        assert data["file"]["mime_type"] == "audio/wav"

        job = data["latest_job"]
        assert job["status"] == "completed"
        audio_data = job["extracted_data"]["data"]
        assert audio_data["duration_seconds"] > 0
        assert len(audio_data["timestamped_segments"]) >= 2
        # Verify timestamp preservation
        seg1 = audio_data["timestamped_segments"][0]
        assert "start" in seg1 and "end" in seg1
        assert seg1["start"] < seg1["end"]

    def test_voice_note_mp3_upload(self):
        """Modality 8: Audio voice note in MP3 format."""
        mp3_bytes = generate_synthetic_mp3_audio()

        response = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("explanation_note.mp3", mp3_bytes, "audio/mpeg")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["file"]["file_type"] == "audio"
        assert data["file"]["mime_type"] == "audio/mpeg"
        assert data["latest_job"]["status"] == "completed"


class TestStorageRetrievalAndLifecycle:
    """Tests file download, preview, reprocessing, and soft deletion."""

    def test_download_and_preview_endpoints(self):
        """Verify binary download and preview return exact uploaded bytes."""
        pdf_bytes = generate_synthetic_text_pdf()

        # Upload
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("bill_to_download.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = up.json()["file"]["id"]

        # Download (attachment)
        down_resp = client.get(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/download",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
        )
        assert down_resp.status_code == 200
        assert down_resp.content == pdf_bytes
        assert "attachment" in down_resp.headers["content-disposition"]
        assert down_resp.headers["content-type"] == "application/pdf"

        # Preview (inline)
        prev_resp = client.get(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/preview",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
        )
        assert prev_resp.status_code == 200
        assert prev_resp.content == pdf_bytes
        assert "inline" in prev_resp.headers["content-disposition"]

    def test_reprocess_evidence_endpoint(self):
        """Verify reprocess creates a fresh completed job."""
        csv_bytes = generate_synthetic_supplier_csv()
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("records.csv", csv_bytes, "text/csv")},
        )
        file_id = up.json()["file"]["id"]

        reproc = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/reprocess",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
        )
        assert reproc.status_code == 200
        assert reproc.json()["latest_job"]["status"] == "completed"

    def test_soft_delete_lifecycle(self):
        """Verify soft deletion hides file from default list without losing data."""
        pdf_bytes = generate_synthetic_text_pdf()
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("to_delete.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = up.json()["file"]["id"]

        # Delete
        del_resp = client.delete(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
        )
        assert del_resp.status_code == 204

        # Regular GET returns 404
        get_resp = client.get(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
        )
        assert get_resp.status_code == 404

        # List without include_deleted does not show file
        list_resp = client.get(
            f"/api/organizations/{ORG_1_ID}/evidence",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
        )
        ids = [f["id"] for f in list_resp.json()["items"]]
        assert file_id not in ids


class TestTenantIsolationAndRBAC:
    """Security tests: cross-tenant denial and role boundary enforcement."""

    def test_tenant_b_cannot_access_tenant_a_evidence(self):
        """Proves strict tenant isolation: Org 2 cannot read or download Org 1 files."""
        pdf_bytes = generate_synthetic_text_pdf()
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("org1_secret_bill.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = up.json()["file"]["id"]

        # Outsider from Org 2 attempts to GET details from Org 1 endpoint -> 403 Forbidden
        outsider_headers = auth_headers(OUTSIDER_2_ID, "user@reliance.com")
        resp = client.get(f"/api/organizations/{ORG_1_ID}/evidence/{file_id}", headers=outsider_headers)
        assert resp.status_code == 403

        # Outsider attempts to download file from Org 1 endpoint -> 403 Forbidden
        down_resp = client.get(f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/download", headers=outsider_headers)
        assert down_resp.status_code == 403

        # Outsider requests file_id under their own org (spoofed path) -> 404 Not Found
        spoof_resp = client.get(f"/api/organizations/{ORG_2_ID}/evidence/{file_id}", headers=outsider_headers)
        assert spoof_resp.status_code == 404

    def test_auditor_role_cannot_upload_or_delete(self):
        """Auditors have read-only access: upload and delete are denied (403)."""
        pdf_bytes = generate_synthetic_text_pdf()
        auditor_headers = auth_headers(AUDITOR_1_ID, "auditor@kpmg.com")

        # Auditor attempts upload -> 403
        up_resp = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auditor_headers,
            files={"file": ("auditor_upload.pdf", pdf_bytes, "application/pdf")},
        )
        assert up_resp.status_code == 403

        # Analyst uploads a file first
        analyst_up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("analyst_bill.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = analyst_up.json()["file"]["id"]

        # Auditor can view, preview, and download
        assert client.get(f"/api/organizations/{ORG_1_ID}/evidence/{file_id}", headers=auditor_headers).status_code == 200
        assert client.get(f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/download", headers=auditor_headers).status_code == 200
        assert client.get(f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/preview", headers=auditor_headers).status_code == 200

        # Auditor attempts delete -> 403
        del_resp = client.delete(f"/api/organizations/{ORG_1_ID}/evidence/{file_id}", headers=auditor_headers)
        assert del_resp.status_code == 403


class TestUploadValidationAndFailures:
    """Edge cases: unsupported media types, spoofing, empty, unauthenticated."""

    def test_unsupported_file_type_rejected_with_415(self):
        """Never silently discard unsupported files: returns 415."""
        binary_junk = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 50

        resp = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("malicious_binary.exe", binary_junk, "application/octet-stream")},
        )
        assert resp.status_code == 415
        assert "Unsupported file format" in resp.json()["detail"]

    def test_extension_spoofing_rejected_with_400(self):
        """Executable binary disguised with .pdf extension is rejected."""
        fake_pdf = b"\x4d\x5a\x90\x00" + b"\x00" * 50  # Windows MZ executable header

        resp = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("fake_electricity_bill.pdf", fake_pdf, "application/pdf")},
        )
        assert resp.status_code == 400
        assert "does not match actual binary file content header" in resp.json()["detail"]

    def test_empty_file_rejected_with_400(self):
        """Zero-byte file is rejected."""
        resp = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_headers(ANALYST_1_ID, "analyst@tata.com"),
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert resp.status_code == 400

    def test_unauthenticated_request_rejected_with_401(self):
        """Requests without Authorization header are rejected."""
        pdf_bytes = generate_synthetic_text_pdf()
        resp = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            files={"file": ("bill.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 401
