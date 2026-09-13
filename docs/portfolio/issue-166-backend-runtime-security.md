# Issue166 — Backend runtime vulnerability refresh

Status: Implemented and locally scanned; protected delivery pending.

## Background and problem

PR163 and the dependent QA PR165 passed functional CI but could not merge because
the required backend image scan failed. Trivy reported12 fixable Debian13
vulnerabilities:9 High and3 Critical. The findings were in the rolling
`python:3.11-slim` base packages, not in the mock OAuth or QA documentation.

## Observation and cause

The failing image contained unfixed-at-install-time revisions including gzip
`1.13-1`, libpcre2 `10.46-1~deb13u1`, libsqlite3 `3.46.1-7+deb13u1`, and
perl-base `5.40.1-6`. Fixed versions were already available from the configured
Debian repositories. Pulling the base image alone reproduced the old revisions,
so rebuilding without a runtime package refresh could not satisfy the gate.

## Solution and safety boundary

The final Docker runtime stage runs `apt-get update`, upgrades installed Debian
packages, removes apt indexes, and then removes pip/setuptools/wheel as before.
The build stage and application dependency boundary are unchanged. The image
still excludes development dependencies and test source.

Rollback is reverting the Dockerfile and its narrow contract assertions. That
rollback would restore the scan failure until the published base image carries
the fixed packages, so it is not an acceptable protected release state.

## Verification

```powershell
docker build --pull --file backend/Dockerfile `
  --tag creativeops-backend:issue166 backend
# PASS; 12 installed OS packages upgraded

docker run --rm creativeops-backend:issue166 `
  dpkg-query -W gzip libpcre2-8-0 libsqlite3-0 perl-base libc6 bash
# gzip 1.13-1+deb13u1
# libpcre2-8-0 10.46-1~deb13u2
# libsqlite3-0 3.46.1-7+deb13u2
# perl-base 5.40.1-6+deb13u1

docker run --rm -v /var/run/docker.sock:/var/run/docker.sock `
  aquasec/trivy:0.70.0 image --ignore-unfixed `
  --severity HIGH,CRITICAL --exit-code 1 --scanners vuln `
  creativeops-backend:issue166
# PASS: Debian and Python package findings 0

cd backend
$env:AI_PROVIDER = "mock"
python -m pytest `
  tests/test_supply_chain_release.py::test_scanned_runtime_images_exclude_development_dependencies -q
# 1 passed
```

Running the whole supply-chain test file on native Windows produced5 passes and
the existing release-script Bash absolute-path failure (`exit127`). That
host-specific failure predates this change and is recorded rather than treated
as a successful full file run.

## Result and remaining risk

The locally rebuilt final backend image has zero High/Critical findings under
the same Trivy severity and fixability policy used by CI. Repository protection
still requires hosted Scan/SBOM and verify results at the pushed PR head. A
future rolling base refresh can introduce new fixable findings; the explicit
runtime upgrade makes the build consume the current Debian security repository
state, so image reproducibility still depends on build time and should later be
paired with scheduled digest refresh evidence.
