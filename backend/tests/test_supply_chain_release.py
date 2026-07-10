from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SUPPLY_CHAIN_WORKFLOW = REPO_ROOT / ".github/workflows/image-supply-chain.yml"
DEPLOY_WORKFLOW = REPO_ROOT / ".github/workflows/deploy-personal-gcp.yml"
BACKEND_BUILD = REPO_ROOT / "infra/gcp/cloudbuild/backend.yaml"
FRONTEND_BUILD = REPO_ROOT / "infra/gcp/cloudbuild/frontend.yaml"
RELEASE_PROFILE = REPO_ROOT / "infra/gcp/release-profile.json"
RELEASE_SCRIPT = REPO_ROOT / "scripts/deploy_gcp_release.sh"
BUILD_HELPER = REPO_ROOT / "scripts/build_push_gcp_images.ps1"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_hosted_supply_chain_workflow_scans_both_images_and_exports_sboms():
    workflow = _text(SUPPLY_CHAIN_WORKFLOW)

    assert "runs-on: ubuntu-24.04" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "service: backend" in workflow
    assert "service: frontend" in workflow
    assert "aquasecurity/trivy-action@" in workflow
    assert "severity: HIGH,CRITICAL" in workflow
    assert 'exit-code: "1"' in workflow
    assert "ignore-unfixed: true" in workflow
    assert "anchore/sbom-action@" in workflow
    assert "format: spdx-json" in workflow
    assert "upload-artifact-retention: 14" in workflow

    action_refs = re.findall(r"uses:\s+[^\s@]+@([^\s]+)", workflow)
    assert action_refs
    assert all(re.fullmatch(r"[a-f0-9]{40}", ref) for ref in action_refs)


def test_cloud_build_requires_verified_provenance_for_both_images():
    for path in (BACKEND_BUILD, FRONTEND_BUILD):
        config = _text(path)
        assert "images:" in config
        assert "- ${_IMAGE}" in config
        assert "requestedVerifyOption: VERIFIED" in config
        assert "docker push" not in config

    helper = _text(BUILD_HELPER)
    assert "cloudbuild/backend.yaml" in helper
    assert "cloudbuild/frontend.yaml" in helper
    assert "gcloud builds submit" in helper
    assert "docker push" not in helper
    assert "if ($NoPush)" in helper


def test_manual_cd_requires_personal_self_hosted_runner_and_digest_inputs():
    workflow = _text(DEPLOY_WORKFLOW)

    assert "workflow_dispatch:" in workflow
    assert "@sha256" in workflow
    assert "runs-on: [self-hosted, linux, x64, creativeops-personal-gcp]" in workflow
    assert "environment: personal-gcp-production" in workflow
    assert "id-token: write" not in workflow
    assert "google-github-actions/auth" not in workflow
    assert "deploy_gcp_release.sh" in workflow

    action_refs = re.findall(r"uses:\s+[^\s@]+@([^\s]+)", workflow)
    assert action_refs
    assert all(re.fullmatch(r"[a-f0-9]{40}", ref) for ref in action_refs)


def test_release_profile_is_non_secret_and_matches_personal_live_topology():
    profile = json.loads(RELEASE_PROFILE.read_text(encoding="utf-8"))

    assert profile["schema_version"] == 1
    assert profile["account"] == "youngjun3108@gmail.com"
    assert profile["project_id"] == "krafton-vertex-live-3108"
    assert profile["terraform_vars"]["ai_provider"] == "mock"
    assert profile["terraform_vars"]["monitoring_alerts_enabled"] is True
    assert profile["terraform_vars"]["monitoring_dashboard_slo_enabled"] is True
    serialized_keys = " ".join(
        list(profile) + list(profile["terraform_vars"])
    ).lower()
    for forbidden in ("password", "private_key", "api_key", "credential", "token"):
        assert forbidden not in serialized_keys


def test_release_script_guards_plan_scope_and_uses_terraform_rollback():
    script = _text(RELEASE_SCRIPT)
    syntax = subprocess.run(
        ["bash", "-n", str(RELEASE_SCRIPT)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert syntax.returncode == 0, syntax.stderr
    assert "youngjun3108@gmail.com" in script
    assert "krafton-vertex-live-3108" in script
    assert "valid_digest_image" in script
    assert "running_digest" in script
    assert 'RELEASE_HEALTH_ATTEMPTS:-12' in script
    assert 'RELEASE_HEALTH_INTERVAL_SEC:-5' in script
    assert "Release health did not converge" in script
    assert '"kubernetes_deployment_v1.api"' in script
    assert '"kubernetes_deployment_v1.worker"' in script
    assert '"kubernetes_deployment_v1.dispatcher"' in script
    assert '"kubernetes_deployment_v1.frontend"' in script
    assert 'show -json "$output_plan"' in script
    assert "Unexpected Terraform release changes" in script
    assert "Candidate verification failed; starting automatic Terraform rollback" in script
    assert 'plan_release "$previous_backend" "$previous_frontend"' in script
    assert "automatic_rollback_complete=true" in script
    assert "kubectl set image" not in script
    assert "rollout undo" not in script

    guard_index = script.index('active_account="$(')
    first_apply_index = script.index(' apply -auto-approve "$plan_file"')
    assert guard_index < first_apply_index
