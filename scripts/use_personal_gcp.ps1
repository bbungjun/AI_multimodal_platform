[CmdletBinding()]
param(
    [string]$ProjectId = "krafton-vertex-live-3108",
    [string]$Region = "asia-northeast3",
    [string]$Zone = "asia-northeast3-a",
    [string]$ImageTag = "portfolio",
    [string]$CloudSdkConfig,
    [string]$Kubeconfig,
    [switch]$SkipVerify
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "gcp_personal_guard.ps1")

if ([string]::IsNullOrWhiteSpace($CloudSdkConfig)) {
    $CloudSdkConfig = Get-CreativeOpsDefaultCloudSdkConfig
}
if ([string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $Kubeconfig = Get-CreativeOpsDefaultKubeconfig
}

Set-CreativeOpsPersonalGcpEnvironment `
    -ProjectId $ProjectId `
    -Region $Region `
    -Zone $Zone `
    -ImageTag $ImageTag `
    -CloudSdkConfig $CloudSdkConfig `
    -Kubeconfig $Kubeconfig

Write-Host "[gcp] CLOUDSDK_CONFIG=$env:CLOUDSDK_CONFIG"
Write-Host "[gcp] KUBECONFIG=$env:KUBECONFIG"
Write-Host "[gcp] Project=$env:GCP_PROJECT_ID Region=$env:GCP_REGION Zone=$env:GCP_ZONE ImageTag=$env:IMAGE_TAG"
Write-Host "[gcp] Cleared GOOGLE_APPLICATION_CREDENTIALS and GOOGLE_APPLICATION_CREDENTIALS_HOST for this session."

if (-not $SkipVerify) {
    Assert-CreativeOpsPersonalGcpContext `
        -ExpectedProject $ProjectId `
        -ExpectedCloudSdkConfig $CloudSdkConfig `
        -ExpectedKubeconfig $Kubeconfig
}
