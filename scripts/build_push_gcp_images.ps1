[CmdletBinding()]
param(
    [string]$ProjectId = "krafton-vertex-live-3108",
    [string]$Region = "asia-northeast3",
    [string]$Zone = "asia-northeast3-a",
    [string]$ImageTag = "portfolio",
    [string]$BackendRepository = "creativeops-portfolio-backend",
    [string]$FrontendRepository = "creativeops-portfolio-frontend",
    [string]$BackendImageName = "creativeops-backend",
    [string]$FrontendImageName = "creativeops-frontend",
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [switch]$NoPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $ScriptDir "..")
. (Join-Path $ScriptDir "gcp_personal_guard.ps1")

foreach ($value in @($ProjectId, $Region, $ImageTag, $BackendRepository, $FrontendRepository, $BackendImageName, $FrontendImageName)) {
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Image build parameters must not be empty."
    }
    if ($value -match "\s") {
        throw "Image build parameters must not contain whitespace: '$value'"
    }
}

Set-CreativeOpsPersonalGcpEnvironment -ProjectId $ProjectId -Region $Region -Zone $Zone -ImageTag $ImageTag
Assert-CreativeOpsPersonalGcpContext -ExpectedProject $ProjectId

$backendImage = "{0}-docker.pkg.dev/{1}/{2}/{3}:{4}" -f $Region, $ProjectId, $BackendRepository, $BackendImageName, $ImageTag
$frontendImage = "{0}-docker.pkg.dev/{1}/{2}/{3}:{4}" -f $Region, $ProjectId, $FrontendRepository, $FrontendImageName, $ImageTag

Push-Location $RepoRoot
try {
    Write-Host "[images] Backend image: $backendImage"
    Write-Host "[images] Frontend image: $frontendImage"

    if (-not $SkipBackend) {
        if ($NoPush) {
            Write-Host "[images] Building backend image locally without push."
            & docker build -t $backendImage ./backend
            if ($LASTEXITCODE -ne 0) {
                throw "Backend local docker build failed."
            }
        }
        else {
            Write-Host "[images] Building backend image with verified Cloud Build provenance."
            & gcloud builds submit ./backend `
                --config infra/gcp/cloudbuild/backend.yaml `
                --substitutions "_IMAGE=$backendImage" `
                --project $ProjectId `
                --quiet
            if ($LASTEXITCODE -ne 0) {
                throw "Backend Cloud Build failed."
            }
        }
    }

    if (-not $SkipFrontend) {
        if ($NoPush) {
            Write-Host "[images] Building frontend image locally without push."
            & docker build -f frontend/Dockerfile.prod -t $frontendImage ./frontend
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend local docker build failed."
            }
        }
        else {
            Write-Host "[images] Building frontend image with verified Cloud Build provenance."
            & gcloud builds submit ./frontend `
                --config infra/gcp/cloudbuild/frontend.yaml `
                --substitutions "_IMAGE=$frontendImage" `
                --project $ProjectId `
                --quiet
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend Cloud Build failed."
            }
        }
    }

    Write-Host "[images] Build step completed."
    Write-Host "[images] Terraform backend_image=$backendImage"
    Write-Host "[images] Terraform frontend_image=$frontendImage"
}
finally {
    Pop-Location
}
