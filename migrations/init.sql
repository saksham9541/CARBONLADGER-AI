-- CarbonLedger AI — Initial PostgreSQL Schema
-- Run automatically by docker-compose on first start.
-- Production migrations are managed by Alembic.

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Organisations
CREATE TABLE IF NOT EXISTS organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    country     TEXT NOT NULL DEFAULT 'IN',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    email           TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'analyst' CHECK (role IN ('analyst','auditor','admin')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Reporting periods
CREATE TABLE IF NOT EXISTS reporting_periods (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id),
    name        TEXT NOT NULL,
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','in_progress','approved','locked')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Evidence files (original documents — immutable after upload)
CREATE TABLE IF NOT EXISTS evidence_files (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    period_id       UUID REFERENCES reporting_periods(id),
    original_name   TEXT NOT NULL,
    storage_path    TEXT NOT NULL,
    file_hash       TEXT NOT NULL,          -- SHA-256 for tamper detection
    file_type       TEXT NOT NULL,          -- pdf|image|excel|audio
    mime_type       TEXT NOT NULL,
    size_bytes      BIGINT NOT NULL,
    uploaded_by     UUID REFERENCES users(id),
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE   -- soft delete only
);

-- Extraction jobs
CREATE TABLE IF NOT EXISTS extraction_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id         UUID NOT NULL REFERENCES evidence_files(id),
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed')),
    model_name      TEXT,
    model_version   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Activity records (extracted + normalised values)
CREATE TABLE IF NOT EXISTS activity_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(id),
    period_id           UUID REFERENCES reporting_periods(id),
    file_id             UUID REFERENCES evidence_files(id),
    job_id              UUID REFERENCES extraction_jobs(id),
    -- Evidence provenance
    evidence_reference  TEXT,       -- page number, cell ref, timestamp
    evidence_type       TEXT NOT NULL, -- electricity|diesel|supplier|audio
    -- Raw extracted values (immutable)
    raw_value           NUMERIC,
    raw_unit            TEXT,
    raw_date_start      DATE,
    raw_date_end        DATE,
    confidence          NUMERIC CHECK (confidence BETWEEN 0 AND 1),
    -- Normalised values (after unit conversion)
    normalised_value    NUMERIC,
    normalised_unit     TEXT,
    -- Status
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','review','approved','rejected','missing_evidence')),
    -- Human correction tracking
    corrected_by        UUID REFERENCES users(id),
    corrected_at        TIMESTAMPTZ,
    correction_note     TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Versioned emission factor files
CREATE TABLE IF NOT EXISTS factor_versions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id),
    file_name   TEXT NOT NULL,
    file_hash   TEXT NOT NULL,
    source      TEXT NOT NULL,      -- CEA | UK-DESNZ | custom
    version     TEXT NOT NULL,
    year        INT NOT NULL,
    geography   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','superseded')),
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Individual emission factors (from approved factor versions)
CREATE TABLE IF NOT EXISTS emission_factors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id      UUID NOT NULL REFERENCES factor_versions(id),
    factor_id       TEXT NOT NULL,      -- e.g. GRID-IN-2026-01
    activity        TEXT NOT NULL,      -- e.g. Purchased electricity
    value           NUMERIC NOT NULL,
    factor_unit     TEXT NOT NULL,      -- e.g. kg CO2e/kWh
    gas_type        TEXT NOT NULL DEFAULT 'CO2e',
    scope           TEXT NOT NULL CHECK (scope IN ('1','2','3')),
    source_ref      TEXT,
    methodology     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Calculation records (immutable — new row on every recalculation)
CREATE TABLE IF NOT EXISTS calculations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(id),
    period_id           UUID NOT NULL REFERENCES reporting_periods(id),
    activity_record_id  UUID NOT NULL REFERENCES activity_records(id),
    factor_id           UUID NOT NULL REFERENCES emission_factors(id),
    -- Inputs (all stored for reproducibility)
    activity_value      NUMERIC NOT NULL,
    activity_unit       TEXT NOT NULL,
    factor_value        NUMERIC NOT NULL,
    factor_unit         TEXT NOT NULL,
    -- Output
    emissions_kg_co2e   NUMERIC NOT NULL,   -- Python Decimal result, stored as NUMERIC
    emissions_t_co2e    NUMERIC NOT NULL,
    scope               TEXT NOT NULL CHECK (scope IN ('1','2','3')),
    formula             TEXT NOT NULL,      -- human-readable formula string
    calc_version        TEXT NOT NULL,      -- engine version for reproducibility
    calculated_by       UUID REFERENCES users(id),
    calculated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Evidence flags (gaps, duplicates, conflicts)
CREATE TABLE IF NOT EXISTS evidence_flags (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    period_id       UUID REFERENCES reporting_periods(id),
    flag_type       TEXT NOT NULL
                    CHECK (flag_type IN (
                        'missing_evidence','duplicate','conflict',
                        'unknown_unit','missing_factor','low_confidence','unsupported_declaration'
                    )),
    description     TEXT NOT NULL,
    record_id       UUID REFERENCES activity_records(id),
    file_id         UUID REFERENCES evidence_files(id),
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','waived')),
    resolved_by     UUID REFERENCES users(id),
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit log (append-only)
CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    org_id      UUID REFERENCES organizations(id),
    user_id     UUID REFERENCES users(id),
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT,
    old_value   JSONB,
    new_value   JSONB,
    ip_address  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_activity_records_period ON activity_records(period_id);
CREATE INDEX IF NOT EXISTS idx_activity_records_file   ON activity_records(file_id);
CREATE INDEX IF NOT EXISTS idx_calculations_period     ON calculations(period_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity       ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_evidence_flags_period   ON evidence_flags(period_id, status);
