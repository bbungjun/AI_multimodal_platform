from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def workflow_text() -> str:
    assert WORKFLOW_PATH.exists(), (
        "Expected CI workflow at .github/workflows/ci.yml. "
        "This test intentionally fixes the GitHub Actions contract before the workflow exists."
    )
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def normalized(text: str) -> str:
    return " ".join(text.split())


def test_ci_workflow_file_exists() -> None:
    assert WORKFLOW_PATH.exists()


def test_ci_workflow_runs_local_verification_script() -> None:
    assert "python scripts/verify_local.py" in workflow_text()


def test_ci_workflow_uses_node_24_compatible_actions() -> None:
    text = workflow_text()

    assert "actions/checkout@v6" in text
    assert "actions/setup-python@v6" in text
    assert "actions/setup-node@v6" in text


def test_ci_workflow_installs_backend_and_frontend_dependencies() -> None:
    text = workflow_text()

    assert 'python -m pip install -e ".[dev]"' in text
    assert "working-directory: backend" in text
    assert "npm ci" in text
    assert "working-directory: frontend" in text


def test_ci_workflow_uses_read_only_permissions_and_mock_provider() -> None:
    text = workflow_text()
    compact = normalized(text)

    assert "permissions:" in text
    assert "contents: read" in text
    assert "AI_PROVIDER: mock" in text
    assert "permissions: contents: read" in compact


def test_ci_workflow_does_not_reference_github_secrets() -> None:
    assert "secrets." not in workflow_text()


def test_ci_workflow_has_required_triggers() -> None:
    text = workflow_text()

    assert "pull_request:" in text
    assert "push:" in text
    assert "workflow_dispatch:" in text
