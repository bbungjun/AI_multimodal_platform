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

    if (-not $NoPush) {
        Write-Host "[images] Configuring Docker auth for $Region-docker.pkg.dev"
        & gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet --project $ProjectId
        if ($LASTEXITCODE -ne 0) {
            throw "gcloud auth configure-docker failed."
        }
    }

    if (-not $SkipBackend) {
        Write-Host "[images] Building backend image."
        & docker build -t $backendImage ./backend
        if ($LASTEXITCODE -ne 0) {
            throw "Backend docker build failed."
        }

        if (-not $NoPush) {
            Write-Host "[images] Pushing backend image."
            & docker push $backendImage
            if ($LASTEXITCODE -ne 0) {
                throw "Backend docker push failed."
            }
        }
    }

    if (-not $SkipFrontend) {
        Write-Host "[images] Building frontend image."
        & docker build -f frontend/Dockerfile.prod -t $frontendImage ./frontend
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend docker build failed."
        }

        if (-not $NoPush) {
            Write-Host "[images] Pushing frontend image."
            & docker push $frontendImage
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend docker push failed."
            }
        }
    }

    Write-Host "[images] Build/push step completed."
    Write-Host "[images] Terraform backend_image=$backendImage"
    Write-Host "[images] Terraform frontend_image=$frontendImage"
}
finally {
    Pop-Location
}
