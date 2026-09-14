#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from registry import load_registry, validate_receipt  # noqa: E402


def pass_receipt(registry):
    results = []
    for scenario in registry.scenarios:
        results.append({
            "scenario_id": scenario["id"],
            "selected": True,
            "verdict": "PASS",
            "assertions": [{"id": row["id"], "passed": True, "evidence": row["evidence"]}
                           for row in scenario["assertions"]],
            "blocked_reasons": [],
        })
    return {
        "schema_version": 1,
        "run_id": "contract-check-001",
        "revision": "0" * 40,
        "registry_sha256": registry.sha256,
        "provider": "mock",
        "source_unchanged": True,
        "scenario_results": results,
        "cleanup": {"browser": 0, "mcp": 0, "vite": 0, "runtime": 0},
        "verdict": "PASS",
    }


def main(argv=None):
    if argv if argv is not None else sys.argv[1:]:
        print('{"complete":false,"error":"arguments_refused"}')
        return 2
    try:
        registry = load_registry()
        validate_receipt(pass_receipt(registry), registry, expected_revision="0" * 40)
    except (OSError, ValueError, UnicodeError) as error:
        print(json.dumps({"complete": False, "error": str(error)}, separators=(",", ":")))
        return 1
    print(json.dumps({"complete": True, "registry_id": registry.metadata["registry_id"],
                      "schema_version": 1, "scenarios": len(registry.scenarios),
                      "assertions": sum(len(row["assertions"]) for row in registry.scenarios),
                      "registry_sha256": registry.sha256, "receipt_contract": True}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
