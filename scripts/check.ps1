#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run every NarraX quality gate and exit non-zero if any fails.

.DESCRIPTION
    Backend: ruff lint, ruff format check, mypy, pytest.
    Frontend: tsc typecheck, eslint.
    The production build (`pnpm build`) is deliberately excluded because it is slow;
    run it separately when preparing a release.

.EXAMPLE
    pwsh -File scripts/check.ps1

.EXAMPLE
    pwsh -File scripts/check.ps1 -BackendOnly
#>
[CmdletBinding()]
param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = 'Continue'

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

$script:failures = 0

function Invoke-Gate {
    param(
        [string]$Label,
        [string]$WorkingDirectory,
        [string]$Executable,
        [string[]]$Arguments
    )
    Write-Host "==> $Label" -ForegroundColor Cyan
    Push-Location $WorkingDirectory
    try {
        & $Executable @Arguments
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($exitCode -ne 0) {
        Write-Host "    FAILED (exit $exitCode)" -ForegroundColor Red
        $script:failures++
    } else {
        Write-Host '    ok' -ForegroundColor Green
    }
}

if (-not $FrontendOnly) {
    $python = Join-Path $backend '.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) { $python = Join-Path $backend '.venv/bin/python' }
    if (-not (Test-Path $python)) {
        Write-Host 'Backend virtualenv not found. Run scripts/bootstrap.ps1 first.' -ForegroundColor Red
        exit 1
    }

    Invoke-Gate 'backend: ruff lint' $backend $python @('-m', 'ruff', 'check', '.')
    Invoke-Gate 'backend: ruff format' $backend $python @('-m', 'ruff', 'format', '--check', '.')
    Invoke-Gate 'backend: mypy' $backend $python @('-m', 'mypy', 'app')
    Invoke-Gate 'backend: pytest' $backend $python @('-m', 'pytest')
}

if (-not $BackendOnly) {
    Invoke-Gate 'frontend: typecheck' $frontend 'pnpm' @('typecheck')
    Invoke-Gate 'frontend: lint' $frontend 'pnpm' @('lint')
}

Write-Host ''
if ($script:failures -gt 0) {
    Write-Host "$script:failures gate(s) failed." -ForegroundColor Red
    exit 1
}
Write-Host 'All gates passed.' -ForegroundColor Green
