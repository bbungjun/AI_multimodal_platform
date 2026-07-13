from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent


class VerificationError(RuntimeError):
    """Raised when the evaluation verification boundary is unsafe."""


def require_mock_provider(environ: Mapping[str, str]) -> None:
    if environ.get("AI_PROVIDER") != "mock":
        raise VerificationError(
            "AI_PROVIDER=mock is required. This command does not load or accept a .env file."
        )


def run_tests(environ: Mapping[str, str]) -> int:
    environment = dict(environ)
    environment["AI_PROVIDER"] = "mock"
    result = subprocess.run(
        [sys.executable, "-m", "pytest"],
        cwd=PACKAGE_ROOT,
        env=environment,
        check=False,
    )
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        print(
            "EVAL VERIFY FAILED: this command accepts no arguments and never loads a .env file.",
            file=sys.stderr,
        )
        return 2
    try:
        require_mock_provider(os.environ)
    except VerificationError as exc:
        print(f"EVAL VERIFY FAILED: {exc}", file=sys.stderr)
        return 2
    return run_tests(os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
