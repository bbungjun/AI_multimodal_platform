import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from smoke_mock_golden_path import SmokeError, parse_env_file  # noqa: E402


class VerifyError(RuntimeError):
    """Raised for expected local verification failures."""


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]
    cwd: Path
    env_overrides: dict[str, str] = field(default_factory=dict)


def validate_env_file(path: Path) -> Path:
    """Validate a mock-only env file without printing its contents."""
    env_path = path.expanduser()
    try:
        parse_env_file(env_path)
    except SmokeError as exc:
        raise VerifyError(f"Env file validation failed: {exc}") from exc
    return env_path


def validate_no_backend_dotenv(repo_root: Path) -> None:
    backend_env = repo_root / "backend" / ".env"
    if backend_env.exists():
        raise VerifyError(
            "Refusing to run backend tests while backend/.env exists. "
            "Move or remove backend/.env before local verification, or use "
            "--skip-backend for compose/frontend-only checks."
        )


def build_steps(repo_root: Path, env_file: Path) -> list[Step]:
    return [
        Step(
            name="Compose config",
            command=[
                "docker",
                "compose",
                "--env-file",
                str(env_file),
                "config",
                "--quiet",
            ],
            cwd=repo_root,
        ),
        Step(
            name="Backend mock tests",
            command=["python", "-m", "pytest"],
            cwd=repo_root / "backend",
            env_overrides={"AI_PROVIDER": "mock"},
        ),
        Step(
            name="Frontend lint",
            command=["npm", "run", "lint"],
            cwd=repo_root / "frontend",
        ),
        Step(
            name="Frontend build",
            command=["npm", "run", "build"],
            cwd=repo_root / "frontend",
        ),
    ]


def _resolve_command(command: list[str]) -> list[str]:
    if os.name == "nt" and command and command[0] == "npm":
        npm_cmd = shutil.which("npm.cmd") or shutil.which("npm")
        if npm_cmd:
            return [npm_cmd, *command[1:]]
    return command


def run_step(step: Step) -> None:
    print(f"[verify] {step.name}", flush=True)
    env = os.environ.copy()
    env.update(step.env_overrides)
    command = _resolve_command(step.command)
    try:
        result = subprocess.run(
            command,
            cwd=step.cwd,
            env=env,
            text=True,
            stdout=None,
            stderr=None,
            check=False,
        )
    except FileNotFoundError as exc:
        raise VerifyError(
            f"{step.name} failed because executable was not found: {exc.filename}"
        ) from exc

    if result.returncode != 0:
        raise VerifyError(f"{step.name} failed with exit code {result.returncode}.")


def _selected_steps(args: argparse.Namespace, repo_root: Path, env_file: Path) -> list[Step]:
    steps = build_steps(repo_root, env_file)
    if args.skip_compose:
        steps = [step for step in steps if step.name != "Compose config"]
    if args.skip_backend:
        steps = [step for step in steps if step.name != "Backend mock tests"]
    if args.skip_frontend:
        steps = [step for step in steps if not step.name.startswith("Frontend ")]
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the local mock quality gate: compose config, backend tests, "
            "and frontend checks."
        )
    )
    parser.add_argument(
        "--env-file",
        default=".env.example",
        help="Mock-only env file for compose config.",
    )
    parser.add_argument(
        "--skip-compose",
        action="store_true",
        help="Skip docker compose config validation.",
    )
    parser.add_argument(
        "--skip-backend",
        action="store_true",
        help="Skip backend mock pytest.",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip frontend lint and build.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    env_file = Path(args.env_file)
    validation_path = env_file if env_file.is_absolute() else repo_root / env_file

    try:
        validate_env_file(validation_path)
        steps = _selected_steps(args, repo_root, env_file)
        if any(step.name == "Backend mock tests" for step in steps):
            validate_no_backend_dotenv(repo_root)
        for step in steps:
            run_step(step)
    except VerifyError as exc:
        print(f"VERIFY FAILED: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("VERIFY FAILED: interrupted", file=sys.stderr)
        return 130

    print("VERIFY PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
