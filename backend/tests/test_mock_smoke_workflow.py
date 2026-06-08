from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "smoke-mock-golden-path.yml"


def workflow_text() -> str:
    assert WORKFLOW_PATH.exists(), (
        "Expected mock golden path smoke workflow at "
        ".github/workflows/smoke-mock-golden-path.yml."
    )
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_mock_smoke_workflow_file_exists() -> None:
    assert WORKFLOW_PATH.exists()


def test_mock_smoke_workflow_is_manual_only() -> None:
    text = workflow_text()

    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "push:" not in text


def test_mock_smoke_workflow_uses_read_only_permissions() -> None:
    text = workflow_text()

    assert "permissions:" in text
    assert "contents: read" in text


def test_mock_smoke_workflow_uses_required_actions_and_python() -> None:
    text = workflow_text()

    assert "actions/checkout@v6" in text
    assert "actions/setup-python@v6" in text
    assert 'python-version: "3.11"' in text


def test_mock_smoke_workflow_forces_mock_provider_without_credentials() -> None:
    text = workflow_text()

    assert "AI_PROVIDER: mock" in text
    assert 'GOOGLE_APPLICATION_CREDENTIALS: ""' in text
    assert "secrets." not in text


def test_mock_smoke_workflow_runs_expected_compose_and_smoke_commands() -> None:
    text = workflow_text()

    assert "docker compose --env-file .env.example config --quiet" in text
    assert (
        "python scripts/smoke_mock_golden_path.py --compose "
        "--env-file .env.example --timeout-sec 90"
    ) in text


def test_mock_smoke_workflow_cleans_up_compose_resources() -> None:
    text = workflow_text()

    assert "if: always()" in text
    assert "docker compose --env-file .env.example down -v" in text


def test_mock_smoke_workflow_does_not_run_other_smoke_scripts() -> None:
    text = workflow_text()

    assert "smoke_mock_retry_flow.py" not in text
    assert "smoke_mock_retry" not in text
