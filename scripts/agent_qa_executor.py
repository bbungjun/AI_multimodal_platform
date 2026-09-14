#!/usr/bin/env python3
"""Run one selection-bound Agent QA scenario through Chrome DevTools MCP."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qa" / "executor"))

from runner import ExecutorError, run_execution  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a selection-bound Agent QA scenario")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--scenario", required=True, choices=["auth_login"])
    args = parser.parse_args(argv)
    try:
        result = run_execution(args.base, args.head, args.scenario)
    except (ExecutorError, OSError, ValueError) as error:
        print(json.dumps({"complete": False, "error": str(error)}, separators=(",", ":")))
        return 1
    summary = {
        "complete": result["complete"],
        "scenario_id": result["scenario_id"] if "scenario_id" in result else result["scenario_result"]["scenario_id"],
        "verdict": result["verdict"] if "verdict" in result else result["scenario_result"]["verdict"],
        "runtime_started": result["runtime_started"],
        "selection_sha256": result["selection_sha256"],
    }
    if "report_path" in result:
        summary["report_path"] = result["report_path"]
        summary["cleanup"] = result["cleanup"]
    print(json.dumps(summary, separators=(",", ":")))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
