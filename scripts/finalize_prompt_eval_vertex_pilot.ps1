[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    [string]$RunId,
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[0-9a-f]{64}$")]
    [string]$ApprovedPlanSha256,
    [string]$ScorerImage = "creativeops-offline-scorers:v2",
    [ValidateSet("auto", "cpu")]
    [string]$Device = "cpu"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$EvalRoot = Join-Path $RepoRoot "evals/prompt_enhancement"
$RunsRoot = Join-Path $EvalRoot "runs"
$RunDir = Join-Path $RunsRoot $RunId
$ModelCache = Join-Path $EvalRoot ".model-cache"

if (-not (Test-Path -LiteralPath (Join-Path $RunDir "manifest.json") -PathType Leaf)) {
    throw "The requested Vertex pilot run does not exist."
}
if (-not (Test-Path -LiteralPath $ModelCache -PathType Container)) {
    throw "The offline scorer model cache is missing. Follow the scorer runbook first."
}

Push-Location $EvalRoot
try {
    docker build -f offline/Dockerfile -t $ScorerImage .
    if ($LASTEXITCODE -ne 0) {
        throw "Offline scorer image build failed."
    }

    docker run --rm --network none `
        -e AI_PROVIDER=vertex `
        -v "${ModelCache}:/model-cache" `
        -v "${RunsRoot}:/runs" `
        $ScorerImage `
        python -m score_real_pairs `
            --run-id $RunId `
            --runs-dir /runs `
            --cache-dir /model-cache `
            --device $Device
    if ($LASTEXITCODE -ne 0) {
        throw "Real scorer execution failed. Resume with the same RunId after diagnosis."
    }

    docker run --rm --network none `
        -e AI_PROVIDER=vertex `
        -v "${RunsRoot}:/runs" `
        $ScorerImage `
        python -m summarize --run-id $RunId --runs-dir /runs
    if ($LASTEXITCODE -ne 0) {
        throw "Paired statistics/report generation failed."
    }

    docker run --rm --network none `
        -e AI_PROVIDER=vertex `
        -v "${RunsRoot}:/runs" `
        $ScorerImage `
        python -m finalize_vertex_pilot `
            --run-id $RunId `
            --runs-dir /runs `
            --approved-plan-sha256 $ApprovedPlanSha256
    if ($LASTEXITCODE -ne 0) {
        throw "Pilot decision/report finalization failed."
    }
}
finally {
    Pop-Location
}
