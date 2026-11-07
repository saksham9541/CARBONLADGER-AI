# CarbonLedger AI

> **Auditable, evidence-driven carbon accounting powered by multimodal AI.**

CarbonLedger AI transforms raw business documents — electricity bills, diesel invoices, supplier declarations, and voice notes — into verifiable GHG inventory reports with a full audit trail from original evidence to final number.

## Core principle

> **AI extracts. Python calculates. Humans approve.**
>
> Gemini performs document understanding and structured data extraction only.
> All carbon arithmetic (Scope 1/2/3 calculations, unit conversions, factor lookups)
> runs in a deterministic Python engine using `Decimal` precision and
> approved, versioned emission factor tables. No LLM output is ever treated as a calculation.

---

## Monorepo structure

```
carbonledger-ai/
├── frontend/               React + TypeScript + Vite + Tailwind CSS + shadcn/ui
│   ├── src/
│   │   ├── components/     Layout, UI primitives (shadcn-compatible)
│   │   ├── pages/          Dashboard, (Phase 2+: Evidence, Ledger, Reports…)
│   │   ├── hooks/          API data hooks (useHealthCheck, etc.)
│   │   └── lib/            api.ts, constants.ts, utils.ts
│   ├── .env.example        Environment variable template
│   └── package.json        Pinned dependencies
│
├── backend/                Python FastAPI
│   ├── app/
│   │   ├── api/routers/    HTTP endpoints (health, evidence, factors, calc…)
│   │   ├── core/           config, logging, exceptions, database
│   │   ├── models/         SQLAlchemy ORM models
│   │   ├── schemas/        Pydantic request/response schemas
│   │   └── services/       extraction, normalization, calculator, reporting…
│   ├── tests/              pytest suite
│   ├── requirements.txt    Pinned production dependencies
│   ├── .env.example        Environment variable template
│   └── main.py             FastAPI application entry point
│
├── migrations/
│   └── init.sql            Initial PostgreSQL schema (all core tables)
│
├── datasets/synthetic/     (Phase 6) Test invoices and ground-truth CSV
│
├── .github/workflows/
│   └── ci.yml              GitHub Actions: lint, type-check, test, build
│
├── docker-compose.yml      PostgreSQL + pgAdmin + Redis (dev)
├── scripts/dev.ps1         Windows-compatible dev commands
├── ARCHITECTURE.md         Full system design and data flow
└── README.md               This file
```

---

## Quick start (Windows)

### Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 20+ |
| Docker Desktop | 4.x+ |
| Git | any recent |

### 1. Clone and configure

```powershell
git clone <repo-url> "CARBONLEDGER AI"
cd "CARBONLEDGER AI"
```

### 2. Start the database

```powershell
docker compose up postgres -d
# PostgreSQL is now on localhost:5432
```

### 3. Start the backend

```powershell
.\scripts\dev.ps1 backend-setup   # Create .venv, install deps
.\scripts\dev.ps1 backend-run     # Start on http://localhost:8000
```

Or manually:
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env as needed
uvicorn main:app --reload --port 8000
```

### 4. Start the frontend

```powershell
.\scripts\dev.ps1 frontend-install  # npm install
.\scripts\dev.ps1 frontend-dev      # Start on http://localhost:5173
```

Or manually:
```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

### 5. Verify everything works

- **Frontend**: http://localhost:5173 — Dashboard with health status
- **Backend API docs**: http://localhost:8000/docs
- **Health endpoint**: http://localhost:8000/api/health

---

## Development commands (dev.ps1)

```powershell
.\scripts\dev.ps1 backend-setup     # Set up Python virtual environment
.\scripts\dev.ps1 backend-run       # Start FastAPI dev server
.\scripts\dev.ps1 backend-test      # Run pytest
.\scripts\dev.ps1 frontend-install  # Install npm packages
.\scripts\dev.ps1 frontend-dev      # Start Vite dev server
.\scripts\dev.ps1 db-up             # Start PostgreSQL
.\scripts\dev.ps1 db-down           # Stop all Docker services
.\scripts\dev.ps1 db-shell          # Open psql shell
.\scripts\dev.ps1 lint-backend      # Run flake8
```

---

## API endpoints (Phase 1 & 2)

| Method | Endpoint | Auth | RBAC Role | Description |
|---|---|---|---|---|
| GET | `/api/health` | None | Public | System and database health check |
| GET | `/docs` | None | Public (dev) | OpenAPI / Swagger interactive documentation |
| POST | `/api/organizations` | Bearer JWT | Authenticated | Create organization (sets creator as Admin) |
| GET | `/api/organizations` | Bearer JWT | Member | List caller's active organizations |
| GET | `/api/organizations/{org_id}` | Bearer JWT | Member | Get organization profile |
| POST | `/api/organizations/{org_id}/members` | Bearer JWT | Admin | Invite/add member to organization |
| GET | `/api/organizations/{org_id}/members` | Bearer JWT | Member | List organization members |
| POST | `/api/organizations/{org_id}/reporting-periods` | Bearer JWT | Admin, Analyst | Create reporting period |
| GET | `/api/organizations/{org_id}/reporting-periods` | Bearer JWT | Member | List organization reporting periods |
| GET | `/api/organizations/{org_id}/reporting-periods/{period_id}` | Bearer JWT | Member | Get reporting period details |
| PATCH | `/api/organizations/{org_id}/reporting-periods/{period_id}` | Bearer JWT | Admin, Analyst | Update reporting period status/dates |

---

## Phase delivery

| Phase | Status | Scope |
|---|---|---|
| 1 — Architecture | ✅ **Complete** | Monorepo, skeleton, health endpoint, DB schema |
| 2 — Database & RBAC | ✅ **Complete** | SQLAlchemy 2, Alembic migrations, Supabase Auth, RBAC, tenant isolation |
| 3 — Multimodal Ingestion | 🔜 Planned | Evidence intake, Supabase storage, Gemini extraction, ledger |
| 4 — Carbon Engine | 🔜 Planned | Unit normalization, factor registry, calculator |
| 5 — Validation & Approval | 🔜 Planned | Gap detection, corrections, audit trail |
| 6 — Reports & AI Features | 🔜 Planned | PDF/Excel, voice summary, analytics |

---

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for:
- Full data flow diagram
- Component responsibilities
- Security boundaries
- Calculation engine contract
- Missing evidence detection logic
- AI extraction boundaries
- Technology decisions
