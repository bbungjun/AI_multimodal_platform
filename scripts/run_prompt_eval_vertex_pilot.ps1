[CmdletBinding()]
param(
    [ValidateSet("Preflight", "Execute")]
    [string]$Mode = "Preflight",
    [string]$PlanPath = "evals/prompt_enhancement/runs/issue66-preflight/preflight.json",
    [string]$ApprovedPlanSha256,
    [string]$MockRunDir = "evals/prompt_enhancement/runs/issue66-mock-dry-run",
    [string]$RunId,
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$EvalRoot = Join-Path $RepoRoot "evals/prompt_enhancement"
$PolicyPath = Join-Path $EvalRoot "pilot_policy.v1.json"

Push-Location $EvalRoot
try {
    if ($Mode -eq "Preflight") {
        python -m pilot --policy $PolicyPath --output (Join-Path $RepoRoot $PlanPath)
        if ($LASTEXITCODE -ne 0) {
            throw "Vertex pilot preflight failed."
        }
        return
    }

    if ([string]::IsNullOrWhiteSpace($ApprovedPlanSha256) -or $ApprovedPlanSha256 -notmatch "^[0-9a-f]{64}$") {
        throw "Execute mode requires the exact approved preflight SHA-256."
    }
    if ([string]::IsNullOrWhiteSpace($RunId)) {
        throw "Execute mode requires an explicit RunId."
    }
    if ($env:AI_PROVIDER -ne "vertex") {
        throw "AI_PROVIDER=vertex is required."
    }
    if ($env:PROVIDER_RETRY_MAX_ATTEMPTS -ne "3") {
        throw "PROVIDER_RETRY_MAX_ATTEMPTS=3 must match the approved policy."
    }
    if ($env:VERTEX_PILOT_EXECUTION_APPROVED -ne "yes") {
        throw "Post-mock execution approval is missing."
    }
    if ($env:VERTEX_PILOT_APPROVED_PLAN_SHA256 -ne $ApprovedPlanSha256) {
        throw "Approved plan environment value does not match the CLI value."
    }

    . (Join-Path $ScriptDir "gcp_personal_guard.ps1")
    Assert-CreativeOpsPersonalGcpContext
    $env:VERTEX_PILOT_GCP_GUARD = "passed"

    python -m run_vertex_pilot `
        --execute `
        --policy $PolicyPath `
        --preflight (Join-Path $RepoRoot $PlanPath) `
        --approved-plan-sha256 $ApprovedPlanSha256 `
        --mock-run-dir (Join-Path $RepoRoot $MockRunDir) `
        --base-url $BaseUrl `
        --run-id $RunId
    if ($LASTEXITCODE -ne 0) {
        throw "Vertex pilot execution failed. Inspect the non-secret run artifacts."
    }
}
finally {
    Pop-Location
}
