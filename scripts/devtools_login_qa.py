"""Interactive, owned mock login proof driven by agent-selected DevTools MCP calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from mock_auth_support import ROOT
from verify_mock_oauth_browser import MockOAuthRuntime
sys.path.insert(0, str(ROOT / "qa" / "executor"))
from prompt_t2i_adapter import read_owned_db_probe


def refusal_deltas(before, after):
    if (set(before) != {"complete", "jobs", "outbox", "reservations"}
            or set(after) != set(before)):
        raise ValueError("probe_counts_invalid")
    expected = {"jobs": 1, "outbox": 1, "reservations": 4}
    return {key: after[key] - before[key] - expected[key]
            for key in ("jobs", "outbox", "reservations")}


def revision():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def source_digest():
    """Fingerprint tracked source plus this verifier, excluding local data and secrets."""
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    paths = set(filter(None, tracked)) | {
        "scripts/devtools_login_qa.py", "qa/devtools/agent.mjs", "qa/devtools/package.json",
        "qa/devtools/package-lock.json",
        "qa/devtools/image-journey.mjs",
    }
    digest = hashlib.sha256()
    for name in sorted(paths):
        # Documentation does not enter the runtime; credentials are never inputs.
        if name.startswith(("docs/", ".omo/")) or name.endswith(".md"):
            continue
        if (Path(name).name.startswith(".env") and name != ".env.example"):
            raise RuntimeError("tracked_dotenv_refused")
        path = ROOT / name
        digest.update(name.encode() + b"\0")
        digest.update(path.read_bytes() if path.is_file() else b"MISSING")
    return digest.hexdigest()


def main():
    args = sys.argv[1:]
    if args not in ([], ["--scenario", "image"], ["--scenario", "image", "--auto"]):
        print('{"complete":false,"error":"arguments_refused"}')
        return 2
    scenario = "image" if args else "login"
    automatic = args == ["--scenario", "image", "--auto"]
    run_id = "devtools-" + scenario + "-" + uuid4().hex[:12]
    output = ROOT / "output" / "playwright" / run_id
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "run_id": run_id, "scenario": scenario, "revision": revision(),
              "source_sha256": source_digest(), "provider": "mock", "complete": False,
              "runtime_cleanup": "not_started"}
    runtime = MockOAuthRuntime(ROOT / ".env.example")
    # Interactive agent actions need a bounded session, not the fixed 180s driver protocol.
    runtime.deadline = time.monotonic() + 1200
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="creativeops-devtools-") as temporary:
            try:
                runtime.preflight()
                print(json.dumps({"phase": "starting_owned_mock", "run_id": run_id}), flush=True)
                runtime.start(temporary)
                probe_before = read_owned_db_probe(runtime, "counts") if automatic else None
                result = subprocess.run(
                    (["node", str(ROOT / "qa/devtools/image-controller.mjs"), runtime.base_url,
                      str(output), str(Path(temporary) / "chrome-profile")]
                     if automatic else
                     ["node", str(ROOT / "qa/devtools/agent.mjs"), runtime.base_url,
                      str(output), str(Path(temporary) / "chrome-profile"), scenario]),
                    cwd=ROOT, env=runtime.env, timeout=720,
                )
                report["driver_exit_code"] = result.returncode
                if automatic:
                    probe_after = read_owned_db_probe(runtime, "counts")
                    report["prompt_t2i_probe"] = {
                        "before": probe_before,
                        "after": probe_after,
                        "refusal_deltas": refusal_deltas(probe_before, probe_after),
                    }
                browser_report = output / "browser.json"
                if browser_report.is_file():
                    report["browser"] = json.loads(browser_report.read_text(encoding="utf-8"))
                report["source_unchanged"] = (
                    report["source_sha256"] == source_digest() and report["revision"] == revision())
            finally:
                report["runtime_cleanup"] = "failed"
                runtime.cleanup()
                report["runtime_cleanup"] = 0
    except (Exception, KeyboardInterrupt) as exc:
        # Arbitrary subprocess/HTTP error text can contain sensitive request details.
        report["error"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "execution_failed"
        report["error_type"] = type(exc).__name__
    report["seconds"] = round(time.monotonic() - started, 3)
    browser = report.get("browser", {})
    report["complete"] = (report.get("driver_exit_code") == 0 and browser.get("passed") is True
                          and browser.get("cleanup") == 0 and report["runtime_cleanup"] == 0
                          and report.get("source_unchanged") is True and "error" not in report)
    (output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"complete": report["complete"], "receipt": str(output.relative_to(ROOT) / "receipt.json"),
                      "runtime_cleanup": report["runtime_cleanup"]}), flush=True)
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
