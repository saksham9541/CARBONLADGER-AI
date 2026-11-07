# CarbonLedger AI — Architecture Document
## Phase 1: Foundation & Design Contracts

---

## 1. System Overview

CarbonLedger AI is an **evidence-driven carbon accounting platform** that transforms raw business documents (electricity bills, diesel invoices, supplier declarations, voice notes) into auditable GHG inventory reports.

### Non-negotiable design rule

> **AI never performs carbon arithmetic.**
>
> The Gemini multimodal model performs document classification and structured data extraction only. All emission factor lookups, unit conversions, Scope 1/2/3 calculations, and GHG Protocol computations run exclusively in the **deterministic Python calculation engine** using Python `Decimal` arithmetic and versioned, approved emission factor tables. No LLM output is ever treated as a numerical calculation result.

---

## 2. High-Level Data Flow

```
Analyst uploads files
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│                   EVIDENCE INTAKE LAYER                  │
│  PDFs · Images · Excel · Audio → validated & hashed      │
│  File hash stored; originals are immutable              │
└──────────────────────┬───────────────────────────────────┘
                       │  evidence_files table
                       ▼
┌──────────────────────────────────────────────────────────┐
│                 AI EXTRACTION ENGINE                     │
│  Gemini multimodal → structured JSON + confidence       │
│  OCR fallback for scanned PDFs                          │
│  Whisper for audio → transcript + timestamps            │
│  → extraction_jobs + activity_records (raw)             │
└──────────────────────┬───────────────────────────────────┘
                       │  confidence < threshold → review queue
                       ▼
┌──────────────────────────────────────────────────────────┐
│              EVIDENCE LEDGER & VALIDATION                │
│  Pydantic schema validation                             │
│  Unit normalization (Decimal, registered conversions)   │
│  Coverage gap detection (billing interval analysis)     │
│  Duplicate/conflict detection                           │
│  → evidence_flags for every anomaly                     │
└──────────────────────┬───────────────────────────────────┘
                       │  approved activity records only
                       ▼
┌──────────────────────────────────────────────────────────┐
│          DETERMINISTIC CALCULATION ENGINE                │
│  Loads approved emission factors (factor_versions)      │
│  Applies formula: Activity × Factor = kg CO2e           │
│  Uses Python Decimal — no floating point                │
│  Stores formula string + all inputs in calculations     │
│  Blocks if factor not found (never estimates)           │
└──────────────────────┬───────────────────────────────────┘
                       │  immutable calculation records
                       ▼
┌──────────────────────────────────────────────────────────┐
│            ANALYST REVIEW & APPROVAL LAYER               │
│  Correction interface (new revision, not overwrite)     │
│  Worksheet approval with digital sign-off               │
│  Audit event written for every action                   │
└──────────────────────┬───────────────────────────────────┘
                       │  approved report
                       ▼
┌──────────────────────────────────────────────────────────┐
│                   REPORT GENERATION                      │
│  PDF (ReportLab) + Excel (openpyxl) export              │
│  Narrative commentary from Gemini (clearly labelled)    │
│  60-second voice summary (Edge TTS / Gemini TTS)        │
│  Calculation worksheet separate from AI commentary      │
└──────────────────────────────────────────────────────────┘
```

---

## 3. Component Responsibilities

### 3.1 Frontend (React + TypeScript)

| Component | Responsibility | What it must NOT do |
|---|---|---|
| Dashboard | Display KPIs from API | Compute any emission value |
| Evidence Upload | File validation, batch upload | Read document content |
| Extraction Review | Display AI output, allow correction | Accept unreviewed AI values |
| Source Ledger | Render provenance links | Modify extraction records |
| Calculation Worksheet | Display formulas and results | Re-compute values |
| Report Export | Trigger backend report generation | Generate report content |

**Principle**: The frontend is a **display layer**. Every number it shows was computed by the Python backend and stored in PostgreSQL.

### 3.2 Backend (Python FastAPI)

| Module | Responsibility |
|---|---|
| `app/api/routers/` | HTTP endpoints, request validation, auth checks |
| `app/services/extraction.py` | Gemini API calls, structured output parsing |
| `app/services/normalization.py` | Unit conversion registry (Decimal, no LLM) |
| `app/services/factor_registry.py` | Load, validate, and serve approved factors |
| `app/services/calculator.py` | **Core calculation engine** — Decimal arithmetic |
| `app/services/validation.py` | Coverage gap detection, duplicate checks |
| `app/services/reporting.py` | PDF/Excel report generation |
| `app/core/config.py` | Settings from environment (pydantic-settings) |
| `app/core/logging.py` | Structured JSON logs (structlog) |
| `app/core/exceptions.py` | Centralized typed exception hierarchy |
| `app/core/database.py` | SQLAlchemy session management |

### 3.3 Database (PostgreSQL)

All tables follow these invariants:
- **Evidence files are immutable** after upload (soft-delete only)
- **Calculation records are immutable** — recalculations create new rows
- **Corrections create new revisions** — original extractions are never overwritten
- **Audit log is append-only** — no UPDATE or DELETE permitted

---

## 4. Security Boundaries

```
PUBLIC INTERNET
      │
      │ HTTPS
      ▼
┌─────────────────┐
│   CDN / Vercel  │  Frontend (static assets, React SPA)
│   (frontend)    │
└────────┬────────┘
         │ HTTPS API calls (CORS-restricted)
         │ Authorization: Bearer <JWT>
         ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI Backend (Render)               │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │  Auth middleware — validates JWT every req  │   │
│  │  Org-scoped queries — no cross-org access   │   │
│  │  Rate limiting — prevents bulk extraction   │   │
│  └─────────────────────────────────────────────┘   │
│                         │                           │
│              ┌──────────┴──────────┐               │
│              ▼                     ▼               │
│  ┌─────────────────┐   ┌─────────────────────┐    │
│  │   PostgreSQL    │   │  Supabase Storage   │    │
│  │  (private VPC)  │   │  (pre-signed URLs)  │    │
│  └─────────────────┘   └─────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │  Gemini API — called server-side ONLY       │   │
│  │  API key NEVER sent to frontend             │   │
│  │  Extraction results stored before display   │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Key security rules:**
1. Gemini API key stored only in backend environment — never in frontend
2. File downloads use short-lived pre-signed URLs, never direct storage paths
3. All database queries are org-scoped (`WHERE org_id = ?`) — users cannot query across organizations
4. JWT tokens expire after 60 minutes; refresh tokens stored in `httpOnly` cookies
5. File uploads are hash-verified on receipt; stored originals are never modified

---

## 5. Calculation Engine Contract

The calculation engine (`app/services/calculator.py`) enforces:

```python
# FORMULA (from GHG Protocol):
# emissions_kg_co2e = activity_value (in normalized unit)
#                   × factor_value (kg CO2e per normalized unit)
#
# emissions_t_co2e = emissions_kg_co2e / 1000

from decimal import Decimal, ROUND_HALF_UP

def calculate(
    activity_value: Decimal,  # from activity_records.normalised_value
    activity_unit: str,        # must match factor denominator unit
    factor: EmissionFactor,    # from approved factor_versions only
) -> CalculationResult:
    # Dimensional check: activity_unit must match factor denominator
    # Raises CalculationBlockedError if units don't match
    # Uses Decimal throughout — no float, no LLM output
    ...
```

**Blocking rules:**
- ❌ No approved factor matching the activity → `CalculationBlockedError`
- ❌ Unit mismatch between activity and factor → `CalculationBlockedError`
- ❌ Missing evidence for a required period → `MissingEvidenceError`
- ❌ Factor version not in `approved` status → `CalculationBlockedError`

**Unit conversion registry** (registered conversions only — no LLM):

| Input | Normalized | Multiplier |
|---|---|---|
| MWh | kWh | × 1,000 |
| kL | L | × 1,000 |
| m³ (liquid) | L | × 1,000 |
| tonne | kg | × 1,000 |
| mile | km | × 1.609344 |

> ⚠️ Fuel invoices in **kg** cannot be auto-converted to **litres** without a documented density. The system will raise `UnitConversionError` and flag the record for analyst resolution.

---

## 6. Missing Evidence Detection

The validation service compares **actual billing intervals** (from `activity_records.raw_date_start` and `raw_date_end`) against the reporting period boundaries.

```
Reporting period: 2026-01-01 → 2026-04-30

Evidence uploaded:
  Jan bill: 2026-01-01 → 2026-01-31  ✓ covered
  Feb bill: 2026-02-01 → 2026-02-28  ✓ covered
  Apr bill: 2026-04-01 → 2026-04-30  ✓ covered

Gap detected:
  2026-03-01 → 2026-03-31  ✗ MISSING_EVIDENCE flag raised

System response:
  - Creates evidence_flag (type=missing_evidence)
  - Marks period status as 'incomplete'
  - Blocks final report approval until resolved
  - Does NOT estimate or fill missing consumption
```

---

## 7. AI Extraction Boundaries

Gemini is permitted to:
- ✅ Classify document type (electricity bill, diesel invoice, etc.)
- ✅ Extract text fields (invoice number, supplier name, dates)
- ✅ Extract numerical values WITH their units (e.g., `2500 kWh`)
- ✅ Return confidence scores for each extracted field
- ✅ Transcribe audio to text with timestamps
- ✅ Identify evidence references (page, cell, region)

Gemini is NOT permitted to:
- ❌ Select or recommend emission factors
- ❌ Perform any arithmetic on extracted values
- ❌ Convert units
- ❌ Estimate or fill missing values
- ❌ Approve or reject activity records
- ❌ Classify a voice note estimate as measured evidence

---

## 8. Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Decimal arithmetic | Python `decimal.Decimal` | Avoids floating-point rounding; required for financial/regulatory reporting |
| Structured logging | structlog | JSON logs in production enable aggregation; human-readable in dev |
| Config management | pydantic-settings | Type-safe, validated settings; `.env` file support |
| ORM | SQLAlchemy 2.0 | Mature, type-safe, supports both sync and async |
| Migrations | Alembic | Version-controlled schema changes |
| Exception hierarchy | Custom typed exceptions | Consistent API error responses; structured logging context |
| CORS | FastAPI middleware | Configurable per-environment; origins from env var |
| Auth (Phase 2) | Supabase Auth + JWT | Managed auth; supports analyst/auditor/admin roles |
| File storage | Supabase Storage | Private buckets, pre-signed URLs, hash verification |
| Extraction model | Gemini 1.5 Pro | Multimodal (PDF, image, audio); structured output |

---

## 9. Phase Delivery Plan

| Phase | Scope | Key Outputs |
|---|---|---|
| **1** ✅ | Architecture, monorepo, health endpoint | This document, working skeleton |
| **2** | File upload, Gemini extraction, evidence ledger | Multimodal ingestion pipeline |
| **3** | Unit normalization, factor registry, calculator | Deterministic emission calculations |
| **4** | Gap detection, analyst corrections, approvals | Full validation & audit trail |
| **5** | PDF/Excel reports, voice summary, analytics | Complete reporting suite |
| **6** | Synthetic dataset tests, CI/CD, deployment | Production-ready system |

---

*Architecture document version: 1.0 — Phase 1 baseline*
*Last updated: 2026-11-07*
