# ============================================================
# CarbonLedger AI — Windows-compatible Makefile equivalent
# Save as: scripts/dev.ps1  (run from repo root)
# Usage:  .\scripts\dev.ps1 <command>
# ============================================================
# Commands:
#   backend-setup     Create venv and install Python deps
#   backend-run       Start FastAPI dev server
#   backend-test      Run pytest
#   frontend-install  Install npm deps
#   frontend-dev      Start Vite dev server
#   db-up             Start PostgreSQL via Docker Compose
#   db-down           Stop PostgreSQL
#   db-shell          Open psql shell
#   lint-backend      Run flake8 + mypy
#   help              Show this help
# ============================================================

param([string]$Command = "help")

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot

function Show-Help {
    Write-Host ""
    Write-Host "CarbonLedger AI — Dev Commands" -ForegroundColor Green
    Write-Host "================================" -ForegroundColor Green
    Write-Host "  backend-setup     Create .venv and install dependencies"
    Write-Host "  backend-run       Start FastAPI on http://localhost:8000"
    Write-Host "  backend-test      Run pytest suite"
    Write-Host "  frontend-install  Install npm packages"
    Write-Host "  frontend-dev      Start Vite on http://localhost:5173"
    Write-Host "  db-up             Start PostgreSQL (Docker)"
    Write-Host "  db-down           Stop PostgreSQL (Docker)"
    Write-Host "  db-shell          Open psql shell"
    Write-Host "  lint-backend      Run flake8"
    Write-Host "  help              Show this message"
    Write-Host ""
}

switch ($Command) {
    "backend-setup" {
        Set-Location "$RootDir\backend"
        python -m venv .venv
        .\.venv\Scripts\Activate.ps1
        pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
        Write-Host "Backend environment ready." -ForegroundColor Green
    }
    "backend-run" {
        Set-Location "$RootDir\backend"
        if (Test-Path ".venv\Scripts\Activate.ps1") { .\.venv\Scripts\Activate.ps1 }
        if (-not (Test-Path ".env")) {
            Copy-Item ".env.example" ".env"
            Write-Host "Copied .env.example to .env — edit it before production use." -ForegroundColor Yellow
        }
        uvicorn main:app --reload --host 0.0.0.0 --port 8000
    }
    "backend-test" {
        Set-Location "$RootDir\backend"
        if (Test-Path ".venv\Scripts\Activate.ps1") { .\.venv\Scripts\Activate.ps1 }
        pytest tests/ -v
    }
    "frontend-install" {
        Set-Location "$RootDir\frontend"
        npm install
    }
    "frontend-dev" {
        Set-Location "$RootDir\frontend"
        if (-not (Test-Path ".env.local")) {
            Copy-Item ".env.example" ".env.local"
            Write-Host "Copied .env.example to .env.local" -ForegroundColor Yellow
        }
        npm run dev
    }
    "db-up" {
        Set-Location $RootDir
        docker compose up postgres -d
        Write-Host "PostgreSQL running on localhost:5432" -ForegroundColor Green
    }
    "db-down" {
        Set-Location $RootDir
        docker compose down
    }
    "db-shell" {
        docker exec -it carbonledger_postgres psql -U carbonledger -d carbonledger
    }
    "lint-backend" {
        Set-Location "$RootDir\backend"
        if (Test-Path ".venv\Scripts\Activate.ps1") { .\.venv\Scripts\Activate.ps1 }
        flake8 app/ main.py --max-line-length=100
    }
    default { Show-Help }
}
