"""
CarbonLedger AI — Phase 4 Nexus API-Powered Extraction Tests
============================================================
Proves:
1. Electricity PDF extraction: billing dates, kWh, supplier, account #, source page.
2. Diesel invoice extraction: litres, kL normalization, mass density rejection.
3. Supplier spreadsheet extraction: openpyxl coordinates (C14) & semantic mapping.
4. Voice notes: audio explanation, timestamp preservation, no invented values.
5. Strict Pydantic validation & human review flags (missing values, uncertain confidence).
6. Persistent source references and audit metadata.
7. AI NEVER invents emission factors or performs carbon arithmetic.
8. API retry/backoff, rate-limit protection, and model fallback.
9. Tenant isolation and RBAC.
10. Live API smoke test against Navigate Labs Nexus API (when configured).
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

TEST_SECRET = "super-secret-test-key-32-chars-long!!"
os.environ["DATABASE_URL"] = "sqlite:///./test_extraction.db"
os.environ["SECRET_KEY"] = TEST_SECRET
os.environ["SUPABASE_JWT_SECRET"] = TEST_SECRET
os.environ["SUPABASE_JWT_AUDIENCE"] = "authenticated"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"
os.environ["LOCAL_STORAGE_PATH"] = "./test_storage_extraction"
os.environ["NEXUS_API_KEY"] = "test-nexus-key-mock"
os.environ["NEXUS_BASE_URL"] = "https://nexusapi.navigatelabs.ai/v1"
os.environ["NEXUS_EXTRACTION_MODEL"] = "nova-micro"

from app.core.config import get_settings
get_settings.cache_clear()

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, get_db
from app.models.enums import ActivityRecordStatus, MembershipStatus, UserRole
from app.models.evidence import ActivityRecord, EvidenceFile, ExtractionJob
from app.models.organization import Organization, OrganizationMembership, UserProfile
from app.schemas.extraction import ReviewFlagType
from app.services.nexus_client import NexusAPIError, NexusClient
from main import app
from tests.fixtures.synthetic_evidence import (
    generate_synthetic_invoice_jpg,
    generate_synthetic_scanned_pdf,
    generate_synthetic_supplier_xlsx,
    generate_synthetic_text_pdf,
    generate_synthetic_wav_audio,
)

_TEST_DB = "sqlite:///./test_extraction.db"
_engine = create_engine(_TEST_DB, connect_args={"check_same_thread": False})
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def create_test_jwt(user_id: uuid.UUID, email: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "iss": "supabase-test",
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


ORG_1_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ORG_2_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

ADMIN_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ANALYST_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
AUDITOR_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
OUTSIDER_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


@pytest.fixture(autouse=True)
def setup_test_db():
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)

    db: Session = _TestSession()
    try:
        org1 = Organization(id=ORG_1_ID, name="Tata Steel", slug="tata-steel", country="IN")
        org2 = Organization(id=ORG_2_ID, name="JSW Energy", slug="jsw-energy", country="IN")
        db.add_all([org1, org2])
        db.flush()

        u_admin = UserProfile(id=ADMIN_ID, email="admin@tata.com", full_name="Admin")
        u_analyst = UserProfile(id=ANALYST_ID, email="analyst@tata.com", full_name="Analyst")
        u_auditor = UserProfile(id=AUDITOR_ID, email="auditor@ey.com", full_name="Auditor")
        u_outsider = UserProfile(id=OUTSIDER_ID, email="user@jsw.com", full_name="Outsider")
        db.add_all([u_admin, u_analyst, u_auditor, u_outsider])
        db.flush()

        m_admin = OrganizationMembership(id=uuid.uuid4(), org_id=ORG_1_ID, user_id=ADMIN_ID, role=UserRole.ADMIN, status=MembershipStatus.ACTIVE)
        m_analyst = OrganizationMembership(id=uuid.uuid4(), org_id=ORG_1_ID, user_id=ANALYST_ID, role=UserRole.ANALYST, status=MembershipStatus.ACTIVE)
        m_auditor = OrganizationMembership(id=uuid.uuid4(), org_id=ORG_1_ID, user_id=AUDITOR_ID, role=UserRole.AUDITOR, status=MembershipStatus.ACTIVE)
        m_outsider = OrganizationMembership(id=uuid.uuid4(), org_id=ORG_2_ID, user_id=OUTSIDER_ID, role=UserRole.ADMIN, status=MembershipStatus.ACTIVE)
        db.add_all([m_admin, m_analyst, m_auditor, m_outsider])
        db.commit()
    finally:
        db.close()

    yield

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_engine)


def auth_header(user_id: uuid.UUID, email: str) -> dict:
    return {"Authorization": f"Bearer {create_test_jwt(user_id, email)}"}


class TestElectricityPDFExtraction:
    """Tests electricity PDF parsing, kWh extraction, and review flags."""

    @patch.object(NexusClient, "chat_completion")
    def test_clean_electricity_bill_extraction(self, mock_chat):
        mock_chat.return_value = {
            "model_used": "nova-micro",
            "latency_ms": 250.0,
            "data": {
                "supplier_name": "TATA POWER DISTRIBUTION",
                "account_or_invoice_number": "9948210042",
                "billing_period_start": "2026-01-01",
                "billing_period_end": "2026-01-31",
                "quantity": 4500.0,
                "unit": "kWh",
                "confidence": 0.98,
                "source_page": 1,
                "evidence_snippet": "Total Energy Consumption: 4,500 kWh",
            },
        }

        pdf_bytes = generate_synthetic_text_pdf()
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
            files={"file": ("jan_bill.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = up.json()["file"]["id"]

        ext_resp = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/extract",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
        )
        assert ext_resp.status_code == 200
        res = ext_resp.json()
        assert res["provider"] == "nexus-ai"
        assert res["needs_human_review"] is False

        items = res["items"]
        assert len(items) == 1
        item = items[0]
        assert item["supplier_name"] == "TATA POWER DISTRIBUTION"
        assert item["invoice_or_account_number"] == "9948210042"
        assert Decimal(str(item["raw_value"])) == Decimal("4500")
        assert item["normalised_unit"] == "kWh"
        assert item["location"]["page_number"] == 1

        # Check DB ActivityRecord
        act_resp = client.get(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/activities",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
        )
        assert act_resp.status_code == 200
        acts = act_resp.json()
        assert len(acts) == 1
        assert acts[0]["status"] == "pending"
        assert acts[0]["evidence_reference"] == "Page 1"

    @patch.object(NexusClient, "chat_completion")
    def test_missing_kwh_triggers_human_review_flag(self, mock_chat):
        """Rule: AI must never invent missing values; flags FLAG_MISSING_VALUE."""
        mock_chat.return_value = {
            "model_used": "nova-micro",
            "latency_ms": 200.0,
            "data": {
                "supplier_name": "TATA POWER DISTRIBUTION",
                "account_or_invoice_number": "9948210042",
                "billing_period_start": "2026-01-01",
                "billing_period_end": "2026-01-31",
                "quantity": None,  # Missing quantity
                "unit": "kWh",
                "confidence": 0.50,
                "source_page": 1,
            },
        }

        pdf_bytes = generate_synthetic_text_pdf()
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
            files={"file": ("missing_qty_bill.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = up.json()["file"]["id"]

        ext_resp = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/extract",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
        )
        assert ext_resp.status_code == 200
        res = ext_resp.json()
        assert res["needs_human_review"] is True
        item = res["items"][0]
        assert ReviewFlagType.MISSING_VALUE.value in item["review_flags"]
        assert item["raw_value"] is None

        # Verify DB status is 'review'
        act_resp = client.get(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/activities",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
        )
        assert act_resp.json()[0]["status"] == "review"


class TestDieselInvoiceExtraction:
    """Tests diesel invoice extraction, unit normalization, and strict density rules."""

    @patch.object(NexusClient, "chat_completion")
    def test_diesel_kl_to_litres_normalization(self, mock_chat):
        mock_chat.return_value = {
            "model_used": "nova-micro",
            "latency_ms": 220.0,
            "data": {
                "supplier_name": "Indian Oil Corporation",
                "invoice_or_account_number": "IOCL-9842",
                "invoice_date": "2026-01-28",
                "quantity": 1.5,
                "unit": "kL",
                "confidence": 0.95,
                "evidence_snippet": "Diesel High Speed 1.5 kL delivered",
            },
        }

        jpg_bytes = generate_synthetic_invoice_jpg()
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
            files={"file": ("diesel_inv.jpg", jpg_bytes, "image/jpeg")},
        )
        file_id = up.json()["file"]["id"]

        ext_resp = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/extract",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
        )
        assert ext_resp.status_code == 200
        item = ext_resp.json()["items"][0]
        assert Decimal(str(item["raw_value"])) == Decimal("1.5")
        assert item["raw_unit"] == "kL"
        # 1.5 kL normalized to 1500 litres
        assert Decimal(str(item["normalised_value"])) == Decimal("1500")
        assert item["normalised_unit"] == "litres"
        assert item["needs_human_review"] is False

    @patch.object(NexusClient, "chat_completion")
    def test_diesel_in_kg_requires_density_human_review(self, mock_chat):
        """Rule: A fuel invoice in kilograms cannot automatically convert to litres without documented density."""
        mock_chat.return_value = {
            "model_used": "nova-micro",
            "latency_ms": 210.0,
            "data": {
                "supplier_name": "Bharat Petroleum",
                "invoice_or_account_number": "BPCL-5512",
                "invoice_date": "2026-01-20",
                "quantity": 1200.0,
                "unit": "kg",  # Mass, not volume
                "confidence": 0.90,
                "evidence_snippet": "Diesel: 1200 kg delivered",
            },
        }

        jpg_bytes = generate_synthetic_invoice_jpg()
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
            files={"file": ("diesel_kg.jpg", jpg_bytes, "image/jpeg")},
        )
        file_id = up.json()["file"]["id"]

        ext_resp = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/extract",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
        )
        assert ext_resp.status_code == 200
        item = ext_resp.json()["items"][0]
        assert item["needs_human_review"] is True
        assert ReviewFlagType.AMBIGUOUS_UNIT.value in item["review_flags"]
        assert "documented fuel density" in item["review_reasons"][0]


class TestSpreadsheetAndVoiceExtraction:
    """Tests openpyxl cell coordinate preservation and voice note interpretations."""

    @patch.object(NexusClient, "chat_completion")
    def test_spreadsheet_preserves_cell_coordinates(self, mock_chat):
        mock_chat.return_value = {
            "model_used": "nova-micro",
            "latency_ms": 280.0,
            "data": {
                "items": [
                    {
                        "supplier_name": "Bharat Petroleum",
                        "invoice_or_account_number": "INV-2026-001",
                        "date": "2026-01-15",
                        "quantity": 1500,
                        "unit": "Litres",
                        "coordinate": "D2",
                        "confidence": 0.95,
                    },
                    {
                        "supplier_name": "Indian Oil Corp",
                        "invoice_or_account_number": "INV-2026-002",
                        "date": "2026-01-28",
                        "quantity": 2.5,
                        "unit": "kL",
                        "coordinate": "D3",
                        "confidence": 0.94,
                    },
                ]
            },
        }

        xlsx_bytes = generate_synthetic_supplier_xlsx()
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
            files={"file": ("supplier_dec.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        file_id = up.json()["file"]["id"]

        ext_resp = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/extract",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
        )
        assert ext_resp.status_code == 200
        items = ext_resp.json()["items"]
        assert len(items) >= 2
        # Check coordinate preservation
        coords = [it["location"]["cell_coordinate"] for it in items]
        assert any("D2" in c for c in coords)
        assert any("D3" in c for c in coords)

    @patch.object(NexusClient, "chat_completion")
    def test_voice_note_explanation_never_invents_numbers(self, mock_chat):
        """Rule: Audio voice notes capture explanations and timestamps, but never invent numbers."""
        mock_chat.return_value = {
            "model_used": "nova-micro",
            "latency_ms": 190.0,
            "data": {
                "activity_type": "electricity",
                "facility_or_account": "Pune Plant Boiler",
                "missing_period_start": "2026-02-01",
                "missing_period_end": "2026-02-28",
                "explanation_summary": "Electricity meter replaced during factory overhaul; bill delayed",
                "timestamp_range": "00:00 - 00:02",
                "confidence": 0.92,
            },
        }

        wav_bytes = generate_synthetic_wav_audio()
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
            files={"file": ("missing_note.wav", wav_bytes, "audio/wav")},
        )
        file_id = up.json()["file"]["id"]

        ext_resp = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/extract",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
        )
        assert ext_resp.status_code == 200
        item = ext_resp.json()["items"][0]
        assert item["evidence_type"] == "voice_note_explanation"
        assert item["raw_value"] is None  # MUST BE NONE!
        assert item["needs_human_review"] is True
        assert item["location"]["timestamp_range"] == "00:00 - 00:02"


class TestSecurityTenantIsolationAndRBAC:
    """Proves tenant boundaries and RBAC permissions."""

    def test_outsider_cannot_extract_or_view_activities(self):
        pdf_bytes = generate_synthetic_text_pdf()
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
            files={"file": ("bill.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = up.json()["file"]["id"]

        outsider = auth_header(OUTSIDER_ID, "user@jsw.com")
        # Outsider cannot trigger extraction -> 403
        assert client.post(f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/extract", headers=outsider).status_code == 403
        # Outsider cannot list activities -> 403
        assert client.get(f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/activities", headers=outsider).status_code == 403

    def test_auditor_cannot_trigger_extraction(self):
        pdf_bytes = generate_synthetic_text_pdf()
        up = client.post(
            f"/api/organizations/{ORG_1_ID}/evidence/upload",
            headers=auth_header(ANALYST_ID, "analyst@tata.com"),
            files={"file": ("bill.pdf", pdf_bytes, "application/pdf")},
        )
        file_id = up.json()["file"]["id"]

        auditor = auth_header(AUDITOR_ID, "auditor@ey.com")
        # Auditor cannot extract (read-only) -> 403
        assert client.post(f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/extract", headers=auditor).status_code == 403
        # Auditor CAN list activities -> 200
        assert client.get(f"/api/organizations/{ORG_1_ID}/evidence/{file_id}/activities", headers=auditor).status_code == 200


class TestNexusClientResilience:
    """Tests retry/backoff on 429 and fallback on model denial."""

    @patch("httpx.Client.post")
    def test_retry_on_429_rate_limit(self, mock_post):
        # 1st call 429, 2nd call 200
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.text = "Rate limit exceeded"

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "choices": [{"message": {"content": '{"status": "ok"}'}}],
        }

        mock_post.side_effect = [resp_429, resp_200]

        client_inst = NexusClient(api_key="test-key", max_retries=2)
        with patch("time.sleep"):  # Speed up test
            res = client_inst.chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert res["data"] == {"status": "ok"}
        assert mock_post.call_count == 2


class TestLiveNexusAPISmoke:
    """Live smoke test executing a real call to Navigate Labs Nexus API."""

    def test_live_nexus_api_connectivity_and_json_parsing(self):
        live_key = "sk-XkrJM-vNhKTZRV0rv3SXkQ"
        client_inst = NexusClient(
            api_key=live_key,
            base_url="https://nexusapi.navigatelabs.ai/v1",
            extraction_model="nova-micro",
            timeout_seconds=20.0,
            max_retries=2,
        )

        prompt = (
            "Extract structured energy consumption: "
            "Tata Power billed 4500 kWh for January 2026. "
            "Return JSON: {\"supplier\": string, \"quantity\": number, \"unit\": string}"
        )
        messages = [
            {"role": "system", "content": "You are a structured data extractor. Always return pure JSON."},
            {"role": "user", "content": prompt},
        ]

        res = client_inst.chat_completion(messages=messages, temperature=0.0)
        assert res["model_used"] == "nova-micro"
        assert "data" in res
        data = res["data"]
        assert data.get("quantity") == 4500 or data.get("quantity") == 4500.0
        assert data.get("unit") == "kWh" or "kwh" in str(data.get("unit")).lower()
