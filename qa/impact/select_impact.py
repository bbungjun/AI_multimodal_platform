#!/usr/bin/env python3
"""Select Agent QA scenarios for two immutable Git revisions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[1]
CONTRACT_ROOT = HERE.parent / "contracts"
sys.path.insert(0, str(CONTRACT_ROOT))
sys.path.insert(0, str(HERE))

from registry import load_registry  # noqa: E402
from selector import Change, ImpactError, REVISION, load_policy, select_impact  # noqa: E402


def _git(repository_root: Path, arguments: list[str]) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise ImpactError("impact_git_unavailable") from error
    if result.returncode != 0:
        raise ImpactError("impact_git_command_failed")
    return result.stdout


def changes_between(repository_root: Path, base_revision: str, head_revision: str) -> list[Change]:
    if (not REVISION.fullmatch(base_revision) or not REVISION.fullmatch(head_revision)
            or base_revision == head_revision):
        raise ImpactError("impact_revision_invalid")
    for revision in (base_revision, head_revision):
        _git(repository_root, ["cat-file", "-e", revision + "^{commit}"])
    raw = _git(repository_root, [
        "diff", "--name-status", "-z", "--find-renames", "--diff-filter=ACDMRT",
        base_revision, head_revision, "--",
    ])
    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    changes: list[Change] = []
    cursor = 0
    try:
        while cursor < len(tokens):
            status = tokens[cursor].decode("ascii")[0]
            cursor += 1
            if status in {"C", "R"}:
                previous_path = tokens[cursor].decode("utf-8")
                path = tokens[cursor + 1].decode("utf-8")
                cursor += 2
                changes.append(Change(status=status, path=path, previous_path=previous_path))
            else:
                path = tokens[cursor].decode("utf-8")
                cursor += 1
                changes.append(Change(status=status, path=path))
    except (IndexError, UnicodeError) as error:
        raise ImpactError("impact_git_diff_invalid") from error
    return changes


def main(argv: list[str] | None = None, *, repository_root: Path = REPOSITORY_ROOT) -> int:
    parser = argparse.ArgumentParser(description="Select Agent QA scenarios for immutable Git revisions")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    try:
        arguments = parser.parse_args(argv)
        registry = load_registry(CONTRACT_ROOT)
        policy = load_policy(scenario_ids=registry.by_id())
        manifest = select_impact(
            registry,
            policy,
            changes_between(repository_root, arguments.base, arguments.head),
            base_revision=arguments.base,
            head_revision=arguments.head,
        )
    except (ImpactError, OSError, ValueError, UnicodeError) as error:
        print(json.dumps({"complete": False, "error": str(error)}, separators=(",", ":")))
        return 1
    print(json.dumps({"complete": True, **manifest}, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
