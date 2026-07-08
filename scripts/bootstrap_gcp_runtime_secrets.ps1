[CmdletBinding()]
param(
    [string]$ProjectId = "krafton-vertex-live-3108",
    [string]$Region = "asia-northeast3",
    [string]$Zone = "asia-northeast3-a",
    [string]$ProjectName = "creativeops",
    [string]$Environment = "portfolio",
    [string]$DbInstance,
    [string]$DbName = "multimodal",
    [string]$DbUser = "app",
    [string]$DbHost,
    [string]$Namespace,
    [string]$SecretName = "creativeops-runtime-secrets",
    [string]$SecretManagerDatabaseUrlSecret,
    [int]$PasswordBytes = 32,
    [switch]$RefreshKubeconfig,
    [switch]$SkipSecretManagerVersion,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path -LiteralPath (Join-Path $ScriptDir "..")
. (Join-Path $ScriptDir "gcp_personal_guard.ps1")

function New-CreativeOpsUrlSafePassword {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ByteCount
    )

    if ($ByteCount -lt 24) {
        throw "PasswordBytes must be at least 24."
    }

    $bytes = [byte[]]::new($ByteCount)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
}

function Invoke-CreativeOpsGoogleJsonRequest {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("GET", "POST", "PUT")]
        [string]$Method,
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [object]$Body
    )

    $token = & gcloud auth print-access-token --project $ProjectId 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
        throw "Failed to obtain a gcloud access token for the personal account."
    }

    $headers = @{
        Authorization = "Bearer $token"
    }

    if ($PSBoundParameters.ContainsKey("Body")) {
        $json = $Body | ConvertTo-Json -Depth 12
        Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers -ContentType "application/json" -Body $json
    }
    else {
        Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers
    }
}

function Get-CreativeOpsObjectProperty {
    param(
        [object]$Object,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }

    $property.Value
}

function Wait-CreativeOpsCloudSqlOperation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OperationName
    )

    $operationUri = "https://sqladmin.googleapis.com/sql/v1/projects/$ProjectId/operations/$OperationName"
    do {
        Start-Sleep -Seconds 5
        $operation = Invoke-CreativeOpsGoogleJsonRequest -Method "GET" -Uri $operationUri
        $status = [string](Get-CreativeOpsObjectProperty -Object $operation -Name "status")
        if ([string]::IsNullOrWhiteSpace($status)) {
            throw "Cloud SQL operation $OperationName did not return a status."
        }
        Write-Host "[secrets] Cloud SQL operation $OperationName status: $status"
    } while ($status -ne "DONE")

    $operationError = Get-CreativeOpsObjectProperty -Object $operation -Name "error"
    if ($null -ne $operationError) {
        throw "Cloud SQL operation $OperationName failed. Inspect the operation in Google Cloud without printing secret values."
    }
}

function Get-CreativeOpsTerraformOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    Push-Location $RepoRoot
    try {
        $value = & terraform -chdir=infra/gcp output -raw $Name 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value)) {
            throw "Terraform output '$Name' is unavailable. Run this after the GCP stack is applied with remote state initialized."
        }
        ([string]$value).Trim()
    }
    finally {
        Pop-Location
    }
}

$namePrefix = "$ProjectName-$Environment"
if ([string]::IsNullOrWhiteSpace($DbInstance)) {
    $DbInstance = $namePrefix
}
if ([string]::IsNullOrWhiteSpace($Namespace)) {
    $Namespace = $namePrefix
}
if ([string]::IsNullOrWhiteSpace($SecretManagerDatabaseUrlSecret)) {
    $SecretManagerDatabaseUrlSecret = "$namePrefix-database-url"
}

foreach ($value in @($ProjectId, $Region, $Zone, $DbInstance, $DbName, $DbUser, $Namespace, $SecretName, $SecretManagerDatabaseUrlSecret)) {
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Runtime secret parameters must not be empty."
    }
}

Set-CreativeOpsPersonalGcpEnvironment -ProjectId $ProjectId -Region $Region -Zone $Zone
Assert-CreativeOpsPersonalGcpContext -ExpectedProject $ProjectId

if ($DryRun) {
    Write-Host "[secrets] Dry run. No Cloud SQL, Secret Manager, or Kubernetes writes will be made."
    Write-Host "[secrets] Project=$ProjectId Instance=$DbInstance Database=$DbName User=$DbUser Namespace=$Namespace Secret=$SecretName"
    Write-Host "[secrets] Secret Manager secret=$SecretManagerDatabaseUrlSecret"
    return
}

if ([string]::IsNullOrWhiteSpace($DbHost)) {
    $DbHost = Get-CreativeOpsTerraformOutput -Name "cloud_sql_private_ip"
}

if ($RefreshKubeconfig) {
    Write-Host "[secrets] Refreshing kubeconfig for cluster $namePrefix."
    & gcloud container clusters get-credentials $namePrefix --zone $Zone --project $ProjectId
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to refresh kubeconfig for $namePrefix."
    }
}

$dbPassword = New-CreativeOpsUrlSafePassword -ByteCount $PasswordBytes
$encodedUser = [System.Uri]::EscapeDataString($DbUser)
$encodedPassword = [System.Uri]::EscapeDataString($dbPassword)
$encodedDbName = [System.Uri]::EscapeDataString($DbName)
$databaseUrl = "postgresql+asyncpg://${encodedUser}:${encodedPassword}@${DbHost}:5432/${encodedDbName}"

$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("creativeops-secrets-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir | Out-Null

try {
    $usersUri = "https://sqladmin.googleapis.com/sql/v1/projects/$ProjectId/instances/$DbInstance/users"
    $users = Invoke-CreativeOpsGoogleJsonRequest -Method "GET" -Uri $usersUri
    $userItems = Get-CreativeOpsObjectProperty -Object $users -Name "items"
    $existingUser = @($userItems) | Where-Object { (Get-CreativeOpsObjectProperty -Object $_ -Name "name") -eq $DbUser } | Select-Object -First 1
    $body = @{
        name     = $DbUser
        password = $dbPassword
        type     = "BUILT_IN"
    }

    if ($null -eq $existingUser) {
        Write-Host "[secrets] Creating Cloud SQL user '$DbUser' on instance '$DbInstance'."
        $operation = Invoke-CreativeOpsGoogleJsonRequest -Method "POST" -Uri $usersUri -Body $body
    }
    else {
        $encodedDbUserForUri = [System.Uri]::EscapeDataString($DbUser)
        $updateUri = "$usersUri?name=$encodedDbUserForUri"
        Write-Host "[secrets] Rotating Cloud SQL password for user '$DbUser' on instance '$DbInstance'."
        $operation = Invoke-CreativeOpsGoogleJsonRequest -Method "PUT" -Uri $updateUri -Body $body
    }

    $operationName = Get-CreativeOpsObjectProperty -Object $operation -Name "name"
    if ($null -ne $operationName) {
        Wait-CreativeOpsCloudSqlOperation -OperationName $operationName
    }

    $databaseUrlFile = Join-Path $tempDir "DATABASE_URL"
    Set-Content -LiteralPath $databaseUrlFile -Value $databaseUrl -NoNewline -Encoding UTF8

    if (-not $SkipSecretManagerVersion) {
        Write-Host "[secrets] Adding a new Secret Manager version for $SecretManagerDatabaseUrlSecret."
        & gcloud secrets versions add $SecretManagerDatabaseUrlSecret --data-file=$databaseUrlFile --project $ProjectId --quiet
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to add Secret Manager version for $SecretManagerDatabaseUrlSecret."
        }
    }

    Write-Host "[secrets] Applying Kubernetes runtime secret '$SecretName' in namespace '$Namespace'."
    $secretYaml = & kubectl create secret generic $SecretName `
        --namespace $Namespace `
        --from-file=DATABASE_URL=$databaseUrlFile `
        --dry-run=client `
        -o yaml
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to render Kubernetes secret manifest."
    }

    $secretYaml | & kubectl apply -f -
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to apply Kubernetes runtime secret."
    }

    Write-Host "[secrets] Runtime secret refresh completed. No secret values were printed."
}
finally {
    $databaseUrl = $null
    $dbPassword = $null
    $secretYaml = $null
    if (Test-Path -LiteralPath $tempDir) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force
    }
}
