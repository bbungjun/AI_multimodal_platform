from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"


class RepairCliError(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reenqueue pending unblocked generation jobs without reading .env.",
    )
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)

    try:
        _refuse_sensitive_dotenv()
        result = asyncio.run(_run(limit=args.limit))
    except RepairCliError as exc:
        print(f"REENQUEUE FAILED: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("REENQUEUE FAILED: interrupted", file=sys.stderr)
        return 130

    print(
        "REENQUEUE COMPLETE "
        f"selected={result.selected} "
        f"dispatched={result.dispatched} "
        f"failed={result.failed}"
    )
    return 0


def _refuse_sensitive_dotenv() -> None:
    candidates = [
        Path.cwd() / ".env",
        REPO_ROOT / ".env",
        BACKEND_ROOT / ".env",
    ]
    existing = []
    for path in candidates:
        if path.exists() and path not in existing:
            existing.append(path)
    if existing:
        names = ", ".join(str(path) for path in existing)
        raise RepairCliError(
            "Refusing to run while sensitive .env files are present: "
            f"{names}. Provide non-secret environment variables in the process "
            "environment instead."
        )


async def _run(*, limit: int):
    if limit < 1:
        raise RepairCliError("--limit must be at least 1")

    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    from app.services.jobs.repair import reenqueue_pending_jobs

    return await reenqueue_pending_jobs(limit=limit)


if __name__ == "__main__":
    raise SystemExit(main())
