#!/usr/bin/env python3
"""Run exactly two isolated mock browser acceptance cycles."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import time

from browser_acceptance_support import GROUPS, HarnessError, ROOT, run_cycle


def validate_results(results: list[dict]) -> dict:
    if (len(results) != 2 or [row.get("cycle") for row in results] != [1, 2]
            or any(row.get("groups") != len(GROUPS) or row.get("checks", 0) < 80
                   or row.get("external_requests") != 0 or row.get("cleanup") != 0
                   for row in results)):
        raise HarnessError("browser_acceptance_incomplete")
    return {"complete": True, "cycles": 2, "groups": len(GROUPS),
            "checks": sum(row["checks"] for row in results), "cleanup": 0,
            "external_requests": 0}


def main(argv=None) -> int:
    if (argv if argv is not None else sys.argv[1:]):
        print(json.dumps({"complete": False, "error": "arguments_refused"}))
        return 2
    deadline = time.monotonic() + 900
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                  text=True, encoding="utf-8", timeout=10, check=True).stdout.strip()
        if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            raise HarnessError("code_revision_invalid")
        results = []
        for cycle in (1, 2):
            if deadline - time.monotonic() <= 90:
                raise HarnessError("suite_deadline")
            results.append(run_cycle(ROOT / ".env.example", cycle))
        receipt = validate_results(results)
        receipt["code_revision"] = revision
        print(json.dumps(receipt, separators=(",", ":")))
        return 0
    except (HarnessError, OSError, subprocess.SubprocessError) as error:
        code = str(error) if isinstance(error, HarnessError) else "verification_unavailable"
        print(json.dumps({"complete": False, "error": code}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
