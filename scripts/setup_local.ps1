[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$RunVerify,
    [switch]$SkipCompose,
    [switch]$SkipBackend,
    [switch]$SkipFrontend
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $ScriptDir "..")
$EnvExamplePath = Join-Path $RepoRoot ".env.example"
$LocalEnvPath = Join-Path $RepoRoot ".env"

Push-Location $RepoRoot
try {
    Write-Host "[setup] Repository root: $RepoRoot"

    if (-not (Test-Path -LiteralPath $EnvExamplePath)) {
        throw "Missing .env.example at repository root."
    }

    if (Test-Path -LiteralPath $LocalEnvPath) {
        if ($Force) {
            Copy-Item -LiteralPath $EnvExamplePath -Destination $LocalEnvPath -Force
            Write-Host "[setup] Replaced .env from .env.example because -Force was provided."
        }
        else {
            Write-Host "[setup] .env already exists; leaving it untouched."
        }
    }
    else {
        Copy-Item -LiteralPath $EnvExamplePath -Destination $LocalEnvPath -Force
        Write-Host "[setup] Created .env from .env.example."
    }

    if (-not $SkipCompose) {
        Write-Host "[setup] Checking Docker Compose config with .env.example."
        & docker compose --env-file .env.example config --quiet
    }
    else {
        Write-Host "[setup] Skipping Docker Compose config check."
    }

    if ($RunVerify) {
        $verifyArgs = @("scripts/verify_local.py", "--env-file", ".env.example")
        if ($SkipCompose) {
            $verifyArgs += "--skip-compose"
        }
        if ($SkipBackend) {
            $verifyArgs += "--skip-backend"
        }
        if ($SkipFrontend) {
            $verifyArgs += "--skip-frontend"
        }

        Write-Host "[setup] Running local quality gate."
        & python @verifyArgs
    }
    else {
        Write-Host "[setup] Skipping local quality gate. Use -RunVerify to run it."
    }

    Write-Host "[setup] Local setup check completed."
}
finally {
    Pop-Location
}
