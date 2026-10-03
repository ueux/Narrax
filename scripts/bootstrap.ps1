#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Bootstrap a fresh NarraX checkout: database, backend, frontend.

.DESCRIPTION
    Idempotent - safe to re-run. Existing virtualenvs and .env files are left alone.
    Requires: python (3.11+), docker, pnpm.

.EXAMPLE
    pwsh -File scripts/bootstrap.ps1

.EXAMPLE
    pwsh -File scripts/bootstrap.ps1 -SkipDatabase
#>
[CmdletBinding()]
param(
    # Do not start the PostgreSQL container (use when a database is already available).
    [switch]$SkipDatabase,
    # Do not run `pnpm install` for the frontend.
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

function Write-Step { param([string]$Message) Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "    $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "    $Message" -ForegroundColor Yellow }

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

function Invoke-Checked {
    param([string]$Label, [string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed (exit code $LASTEXITCODE)."
    }
}

Write-Step 'Checking prerequisites'
foreach ($command in @('python', 'docker')) { Assert-Command $command }
Write-Ok 'python and docker found'

if (-not $SkipDatabase) {
    Write-Step 'Starting PostgreSQL + pgvector (docker compose)'
    Push-Location $root
    try { Invoke-Checked 'docker compose up' 'docker' @('compose', 'up', '-d') } finally { Pop-Location }
    Write-Ok 'database container started (or already running)'
}

Write-Step 'Backend: virtual environment'
Push-Location $backend
try {
    if (-not (Test-Path '.venv')) { Invoke-Checked 'venv creation' 'python' @('-m', 'venv', '.venv') }

    $python = Join-Path $backend '.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) { $python = Join-Path $backend '.venv/bin/python' }
    if (-not (Test-Path $python)) { throw 'Could not locate the virtualenv interpreter.' }

    Write-Step 'Backend: installing dependencies (editable + dev + db-test extras)'
    Invoke-Checked 'pip upgrade' $python @('-m', 'pip', 'install', '--upgrade', 'pip')
    Invoke-Checked 'pip install -e .[dev,db-test]' $python @(
        '-m', 'pip', 'install', '-e', '.[dev,db-test]'
    )

    if (-not (Test-Path '.env')) {
        Copy-Item (Join-Path $root '.env.example') '.env'
        Write-Ok 'created backend/.env from .env.example (review the values)'
    } else {
        Write-Warn 'backend/.env already exists - left unchanged'
    }

    if ($SkipDatabase) {
        Write-Warn 'skipping migrations (-SkipDatabase)'
    } else {
        Write-Step 'Backend: applying migrations'
        Invoke-Checked 'alembic upgrade head' $python @('-m', 'alembic', 'upgrade', 'head')
    }
} finally { Pop-Location }

if (-not $SkipFrontend) {
    Write-Step 'Frontend: pnpm install'
    Assert-Command 'pnpm'
    Push-Location $frontend
    try { Invoke-Checked 'pnpm install' 'pnpm' @('install') } finally { Pop-Location }
}

Write-Host ''
Write-Host 'Bootstrap complete.' -ForegroundColor Green
Write-Host 'Next steps:'
Write-Host '  pwsh -File scripts/check.ps1                                   # quality gates'
Write-Host '  cd backend; .venv\Scripts\activate; uvicorn app.main:app --reload'
Write-Host '  cd frontend; pnpm dev'
Write-Host '  Open http://localhost:8000/docs and http://localhost:3000'
