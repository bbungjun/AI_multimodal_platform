Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = git rev-parse --show-toplevel
Set-Location (Join-Path $repoRoot "infra/gcp")

terraform init -backend=false
terraform fmt -recursive -check
terraform validate
