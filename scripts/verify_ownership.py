"""Run the credential-free G4 harness; no product login or external services."""
import argparse
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

from mock_auth_support import HarnessError, ROOT, verify_cycles


def scenarios(runtime, identity):
    import smoke_mock_golden_path as golden
    import smoke_mock_retry_flow as retry
    import smoke_mock_i2v_duplicate_guard as duplicate
    for module in (golden, retry, duplicate):
        remaining = runtime.deadline - time.monotonic()
        if remaining <= 0:
            raise HarnessError("cycle_deadline")
        args = SimpleNamespace(timeout_sec=min(90, remaining), poll_interval_sec=0.5,
                               keep_job=False, keep_jobs=False)
        module.run_smoke(args, client=identity.client(runtime.base_url, "a"))
    return 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.example")
    parser.add_argument("--cycles", type=int, choices=(1, 2), default=2)
    args = parser.parse_args(argv)
    try:
        results = verify_cycles(args.env_file, args.cycles, scenario=scenarios)
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"phase": "preflight", "provider": "mock", "passed": False}), file=sys.stderr)
        return 1
    return 0 if len(results) == args.cycles and all(row["passed"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
