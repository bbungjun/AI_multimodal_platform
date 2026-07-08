Set-StrictMode -Version Latest

$script:CreativeOpsExpectedGcpAccount = "youngjun3108@gmail.com"
$script:CreativeOpsExpectedGcpProject = "krafton-vertex-live-3108"
$script:CreativeOpsDefaultRegion = "asia-northeast3"
$script:CreativeOpsDefaultZone = "asia-northeast3-a"
$script:CreativeOpsDefaultImageTag = "portfolio"
$script:CreativeOpsBlockedGcpAccounts = @("sk.yaho2026@gmail.com")
$script:CreativeOpsBlockedGcpProjects = @("ar-infra-501607")

function Get-CreativeOpsDefaultCloudSdkConfig {
    Join-Path $HOME ".gcloud-creativeops-personal"
}

function Get-CreativeOpsDefaultKubeconfig {
    Join-Path (Join-Path $HOME ".kube") "creativeops-personal"
}

function ConvertTo-CreativeOpsNormalizedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    try {
        [System.IO.Path]::GetFullPath($Path).TrimEnd(@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar))
    }
    catch {
        $Path.TrimEnd("\", "/")
    }
}

function Set-CreativeOpsPersonalGcpEnvironment {
    [CmdletBinding()]
    param(
        [string]$ProjectId = $script:CreativeOpsExpectedGcpProject,
        [string]$Region = $script:CreativeOpsDefaultRegion,
        [string]$Zone = $script:CreativeOpsDefaultZone,
        [string]$ImageTag = $script:CreativeOpsDefaultImageTag,
        [string]$CloudSdkConfig = (Get-CreativeOpsDefaultCloudSdkConfig),
        [string]$Kubeconfig = (Get-CreativeOpsDefaultKubeconfig)
    )

    if ($ProjectId -ne $script:CreativeOpsExpectedGcpProject) {
        throw "This repository is pinned to personal GCP project '$($script:CreativeOpsExpectedGcpProject)'. Refusing project '$ProjectId'."
    }

    $env:CLOUDSDK_CONFIG = $CloudSdkConfig
    $env:KUBECONFIG = $Kubeconfig
    Remove-Item Env:\GOOGLE_APPLICATION_CREDENTIALS -ErrorAction SilentlyContinue
    Remove-Item Env:\GOOGLE_APPLICATION_CREDENTIALS_HOST -ErrorAction SilentlyContinue

    $env:GOOGLE_CLOUD_PROJECT = $ProjectId
    $env:CLOUDSDK_CORE_PROJECT = $ProjectId
    $env:TF_VAR_gcp_project_id = $ProjectId
    $env:GCP_PROJECT_ID = $ProjectId
    $env:GCP_REGION = $Region
    $env:GCP_ZONE = $Zone
    $env:IMAGE_TAG = $ImageTag
}

function Get-CreativeOpsGcloudConfigValue {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("account", "project")]
        [string]$Name
    )

    if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
        throw "gcloud is not available on PATH."
    }

    $value = & gcloud config get-value $Name 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read gcloud config value '$Name'."
    }

    $text = ($value | Select-Object -Last 1)
    if ($null -eq $text) {
        return ""
    }

    ([string]$text).Trim()
}

function Assert-CreativeOpsPersonalGcpContext {
    [CmdletBinding()]
    param(
        [string]$ExpectedAccount = $script:CreativeOpsExpectedGcpAccount,
        [string]$ExpectedProject = $script:CreativeOpsExpectedGcpProject,
        [string]$ExpectedCloudSdkConfig = (Get-CreativeOpsDefaultCloudSdkConfig),
        [string]$ExpectedKubeconfig = (Get-CreativeOpsDefaultKubeconfig)
    )

    if ([string]::IsNullOrWhiteSpace($env:CLOUDSDK_CONFIG)) {
        throw "CLOUDSDK_CONFIG is not set. Run scripts/use_personal_gcp.ps1 first."
    }
    if ([string]::IsNullOrWhiteSpace($env:KUBECONFIG)) {
        throw "KUBECONFIG is not set. Run scripts/use_personal_gcp.ps1 first."
    }
    if (-not [string]::IsNullOrWhiteSpace($env:GOOGLE_APPLICATION_CREDENTIALS)) {
        throw "GOOGLE_APPLICATION_CREDENTIALS is set. Refusing to continue for this repo."
    }
    if (-not [string]::IsNullOrWhiteSpace($env:GOOGLE_APPLICATION_CREDENTIALS_HOST)) {
        throw "GOOGLE_APPLICATION_CREDENTIALS_HOST is set. Refusing to continue for this repo."
    }

    $actualCloudSdkConfig = ConvertTo-CreativeOpsNormalizedPath $env:CLOUDSDK_CONFIG
    $expectedCloudSdkConfig = ConvertTo-CreativeOpsNormalizedPath $ExpectedCloudSdkConfig
    if ($actualCloudSdkConfig -ine $expectedCloudSdkConfig) {
        throw "CLOUDSDK_CONFIG must point to the personal CreativeOps config directory. Actual: $env:CLOUDSDK_CONFIG"
    }

    $actualKubeconfig = ConvertTo-CreativeOpsNormalizedPath $env:KUBECONFIG
    $expectedKubeconfig = ConvertTo-CreativeOpsNormalizedPath $ExpectedKubeconfig
    if ($actualKubeconfig -ine $expectedKubeconfig) {
        throw "KUBECONFIG must point to the personal CreativeOps kubeconfig. Actual: $env:KUBECONFIG"
    }

    foreach ($name in @("GOOGLE_CLOUD_PROJECT", "CLOUDSDK_CORE_PROJECT", "TF_VAR_gcp_project_id", "GCP_PROJECT_ID")) {
        $actual = [System.Environment]::GetEnvironmentVariable($name)
        if ($actual -ne $ExpectedProject) {
            throw "$name must be '$ExpectedProject'. Actual: '$actual'"
        }
    }

    $account = Get-CreativeOpsGcloudConfigValue -Name "account"
    $project = Get-CreativeOpsGcloudConfigValue -Name "project"

    if ($script:CreativeOpsBlockedGcpAccounts -contains $account) {
        throw "Refusing to use blocked/team GCP account '$account'."
    }
    if ($script:CreativeOpsBlockedGcpProjects -contains $project) {
        throw "Refusing to use blocked/team GCP project '$project'."
    }
    if ($account -ne $ExpectedAccount) {
        throw "Expected personal GCP account '$ExpectedAccount', but gcloud is using '$account'."
    }
    if ($project -ne $ExpectedProject) {
        throw "Expected personal GCP project '$ExpectedProject', but gcloud is using '$project'."
    }

    Write-Host "[gcp-guard] Verified personal GCP context: $account / $project"
}
