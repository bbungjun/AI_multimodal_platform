from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "setup_local.ps1"


def test_setup_local_script_exists():
    assert SCRIPT_PATH.exists()


def test_setup_local_script_preserves_existing_dotenv_by_default():
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "Test-Path -LiteralPath $LocalEnvPath" in text
    assert "leaving it untouched" in text
    assert "Copy-Item -LiteralPath $EnvExamplePath -Destination $LocalEnvPath -Force" in text
    assert "if ($Force)" in text


def test_setup_local_script_runs_compose_config_with_env_example():
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "docker" in text
    assert "compose" in text
    assert "--env-file" in text
    assert ".env.example" in text
    assert "config" in text
    assert "--quiet" in text


def test_setup_local_script_optionally_delegates_quality_gate_to_verify_local():
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "python" in text
    assert "scripts/verify_local.py" in text
    assert "[switch]$RunVerify" in text
    assert "if ($RunVerify)" in text
    assert "--skip-backend" in text
    assert "--skip-frontend" in text
    assert "--skip-compose" in text
