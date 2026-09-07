#!/usr/bin/env python3
"""Bounded local browser/load/recovery proof. No developer or cloud targets."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import secrets
import re
import subprocess
import tempfile
import time
from urllib.request import Request

from browser_acceptance_support import BrowserRuntime, FRONTEND_ORIGIN
from mock_auth_support import HarnessError, MemoryIdentity, ROOT, http_transport

PROFILES = {
    "baseline": dict(rate=1, time_unit="2s", duration="20s", vus=4),
    "steady": dict(rate=2, time_unit="1s", duration="30s", vus=20),
    "burst": dict(rate=10, time_unit="1s", duration="10s", vus=50),
    "soak": dict(rate=2, time_unit="1s", duration="120s", vus=20),
}


class LoadRuntime(BrowserRuntime):
    def __init__(self, env_file):
        super().__init__(env_file)
        self.deadline = time.monotonic() + 1800

    def fixture(self, operation, hashes=None):
        self.assert_owned()
        value = self.docker(*self.compose, "exec", "-T", "backend", "python",
            "tests/user_journey_fixtures.py", input=json.dumps({"project": self.project,
                "operation": operation, "hashes": hashes or []}))
        result = json.loads(value)
        if "error" in result:
            kind = result.get("kind", "unknown")
            if not isinstance(kind, str) or not kind.isalpha():
                kind = "unknown"
            code = result.get("code", "unknown")
            if not isinstance(code, str) or not code.replace('_', '').isalpha():
                code = "unknown"
            raise HarnessError(f"load_fixture_{kind}_{code}_line_{int(result.get('line', 0))}")
        return result

    def sample(self):
        result = self.fixture("snapshot")
        result["queue_length"] = int(self.docker(*self.compose, "exec", "-T", "redis",
                                                "redis-cli", "llen", "generation"))
        return result

    def resource_sample(self):
        ids = self.docker(*self.compose, "ps", "-q", "backend", "worker", "dispatcher", "db", "redis").splitlines()
        output = self.docker("stats", "--no-stream", "--format", '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}', *ids)
        result = {}
        for line in output.splitlines():
            name, cpu, memory = line.split('|')
            match = re.fullmatch(re.escape(self.project) + r'-(backend|worker|dispatcher|db|redis)-1', name)
            if not match or not re.fullmatch(r'[0-9.]+%', cpu) or not re.fullmatch(r'[0-9.A-Za-z /]+', memory):
                raise HarnessError('unsafe_resource_sample')
            result[match[1]] = {'cpu_percent': float(cpu[:-1]), 'memory': memory}
        return result

    def clock_regressions(self):
        # Retain only the count of this exact bounded diagnostic, never raw logs.
        container = self.docker(*self.compose, "ps", "-q", "backend")
        result = subprocess.run(['docker', '--context', self.context, 'logs', container],
            env=self.env, capture_output=True, text=True, encoding='utf-8', timeout=15)
        return (result.stdout + result.stderr).count('Credit lifecycle rejected a regressed operation clock.')

    def terminal_clock_diagnostics(self):
        diagnostics = []
        for service in ('backend', 'worker'):
            container = self.docker(*self.compose, 'ps', '-q', service)
            result = subprocess.run(['docker', '--context', self.context, 'logs', container],
                env=self.env, capture_output=True, text=True, encoding='utf-8', timeout=15)
            diagnostics += [{'service': service, 'source': source, 'lag_us': int(lag)}
                for source, lag in re.findall(r'Credit terminal rejected a regressed operation clock source=(live|fixed) lag_us=([0-9]+)',
                    result.stdout + result.stderr)]
        return diagnostics


def drained(snapshot):
    return (not sum(v for k, v in snapshot["jobs"].items() if k not in {"completed", "failed"})
        and snapshot["outbox"].get("pending", 0) == 0
        and snapshot["outbox"].get("failed", 0) == 0
        and snapshot["reservations"].get("held", 0) == 0
        and snapshot["held_microcredits"] == 0)


def wait_drain(runtime, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        snapshot = runtime.sample()
        if drained(snapshot) and snapshot["queue_length"] == 0:
            return snapshot
        time.sleep(1)
    return snapshot  # Preserve stranded state as evidence; caller must fail the gate.


def run_load(runtime, sessions, profile, observer=None):
    config = {"base": runtime.base_url, "sessions": sessions, **PROFILES[profile]}
    env = dict(runtime.env, CREATIVEOPS_LOAD_CONFIG=json.dumps(config), K6_NO_USAGE_REPORT="true")
    before = runtime.sample()
    started = time.monotonic()
    samples = []
    process = subprocess.Popen(["k6", "run", "--quiet", "--no-color",
        str(ROOT / "scripts/k6/user_journeys.js")], env=env, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    browser_pool = ThreadPoolExecutor(max_workers=1) if observer else None
    browser_future = None
    browser_result = None
    try:
        while True:
            try:
                output, errors = process.communicate(timeout=5)
                break
            except subprocess.TimeoutExpired:
                if observer and browser_future is None:
                    browser_future = browser_pool.submit(observer)
                samples.append({"elapsed_s": round(time.monotonic() - started, 2),
                                **runtime.sample(), "resources": runtime.resource_sample()})
                if time.monotonic() - started > 230:
                    raise HarnessError("load_deadline")
        if browser_future:
            try:
                browser_result = browser_future.result(timeout=150)
            except Exception:
                browser_result = {"passed": False}
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
        if browser_pool:
            browser_pool.shutdown(wait=True)
    # Suppress raw stderr because tool/network exceptions may include data-bearing URLs.
    try:
        metrics = json.loads(output)["metrics"]
    except (ValueError, KeyError):
        raise HarnessError("k6_aggregate_missing") from None
    after = wait_drain(runtime)
    audit = runtime.fixture("audit")
    thresholds = {name: value["thresholds"] for name, value in metrics.items() if value.get("thresholds")}
    passed = (process.returncode == 0 and drained(after) and after["queue_length"] == 0
              and after["jobs"].get("failed", 0) == 0 and audit["duplicate_asset_jobs"] == 0
              and (not observer or bool(browser_result and browser_result.get("passed"))))
    return {"profile": profile, "configuration": PROFILES[profile], "passed": passed,
        "seconds": round(time.monotonic() - started, 3), "k6_exit": process.returncode,
        "before": before, "samples": samples, "after": after, "audit": audit,
        "thresholds": thresholds, "metrics": metrics, "browser_under_load": browser_result,
        "terminal_clock_diagnostics": runtime.terminal_clock_diagnostics()}


def run_recovery(runtime, sessions):
    runtime.assert_owned()
    before = runtime.sample()
    runtime.docker(*runtime.compose, "stop", "dispatcher")
    payload = {"mode": "t2i", "model": "imagen-4.0-fast-generate-001",
               "prompt": "A blue ceramic cup", "number_of_images": 1}
    def submit(secret):
        body, _, status = http_transport(Request(runtime.base_url + "/api/generations",
            data=json.dumps(payload).encode(), method="POST", headers={
                "Content-Type": "application/json", "Origin": FRONTEND_ORIGIN,
                "Cookie": "creativeops_session=" + secret}))
        code = 'accepted'
        if status != 201:
            try:
                detail = json.loads(body).get('detail')
                code = detail.get('code') if isinstance(detail, dict) else detail
            except (ValueError, AttributeError):
                code = 'unclassified'
            if not isinstance(code, str) or not re.fullmatch(r'(credit_|user_|monthly_)[a-z_]{1,64}', code):
                code = 'unclassified'
        return status, code
    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            submitted = list(pool.map(submit, sessions[:20]))
        with ThreadPoolExecutor(max_workers=10) as pool:
            burst_results = list(pool.map(submit, [sessions[30]] * 10))
        during = runtime.sample()
    finally:
        runtime.docker(*runtime.compose, "start", "dispatcher")
    restarted = time.monotonic()
    after = wait_drain(runtime)
    audit = runtime.fixture("audit")
    statuses = [item[0] for item in submitted]
    burst = [item[0] for item in burst_results]
    passed = (statuses.count(201) == 20 and burst.count(201) == 5 and burst.count(429) == 5
        and during["outbox"].get("pending", 0) == 25
        and during["reservations"].get("held", 0) == 25
        and drained(after) and after["queue_length"] == 0
        and after["jobs"].get("completed", 0) - before["jobs"].get("completed", 0) == 25
        and audit["duplicate_asset_jobs"] == 0)
    return {"profile": "recovery", "passed": passed, "accepted": statuses.count(201),
        "same_user_accepted": burst.count(201), "same_user_429": burst.count(429),
        "same_user_codes": {code: sum(c == code for _, c in burst_results) for _, code in burst_results},
        "clock_regressions": runtime.clock_regressions(),
        "recovery_seconds": round(time.monotonic() - restarted, 3),
        "before": before, "during": during, "after": after, "audit": audit}


def browser(runtime, identity):
    result = subprocess.run(["node", "scripts/user-journey-browser.mjs"], cwd=ROOT / "frontend",
        env=runtime.env, input=json.dumps({"backend_url": runtime.base_url,
            "secret": identity._secrets["a"]}), capture_output=True, text=True, timeout=150)
    try:
        receipt = json.loads(result.stdout)
    except ValueError:
        raise HarnessError("browser_receipt_missing") from None
    if result.returncode or not receipt.get("passed"):
        # The driver exposes a bounded phase, never the raw exception or response.
        phase = receipt.get("phase", "unknown")
        if phase not in {"startup", "enhance", "generate", "download", "library", "usage"}:
            phase = "unknown"
        raise HarnessError("browser_failed_" + phase)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", nargs="+", choices=[*PROFILES, "recovery"], default=[*PROFILES, "recovery"])
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    if len(args.profiles) != len(set(args.profiles)):
        parser.error("profiles must be unique")
    runtime = LoadRuntime(ROOT / ".env.example")
    identity = MemoryIdentity()
    sessions = [secrets.token_urlsafe(32) for _ in range(64)]
    output = ROOT / "output/load" / time.strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=False)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tracked_dirty = bool(subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=ROOT, text=True).strip())
    report = {"revision": revision, "tracked_dirty": tracked_dirty, "provider": "mock",
        "environment": "isolated local Docker", "profiles": [], "cleanup": None,
        "owned_project": runtime.project, "ownership_label": runtime._label,
        "resources": {"api_processes": 1, "dispatcher_processes": 1, "worker_concurrency": 2,
            "model_rate_limits_per_min": 600, "poll_interval_s": 0.5,
            "fixture_users": 64, "plan": "max"}}
    source_paths = ["scripts/verify_user_journey_load.py", "scripts/k6/user_journeys.js",
        "backend/tests/user_journey_fixtures.py", "frontend/scripts/user-journey-browser.mjs",
        "backend/app/db.py", "backend/app/credit_accounting.py", "backend/app/credit_lifecycle.py",
        "backend/app/generation_credit.py", "backend/app/prompt_credit.py", "backend/app/personal_usage.py",
        "backend/app/api/generations.py", "backend/app/api/pipelines.py", "backend/app/api/usage.py",
        "backend/app/services/jobs/handlers.py", "backend/app/services/jobs/pipeline_link.py"]
    report["source_sha256"] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths}
    phase = "preflight"
    try:
        with tempfile.TemporaryDirectory(prefix="creativeops-load-") as directory:
            try:
                runtime.preflight()
                machine = runtime.docker("info", "--format", '{{json .NCPU}} {{json .MemTotal}}')
                cpus, memory = machine.split()
                report["resources"].update(docker_cpus=int(cpus), docker_memory_bytes=int(memory))
                phase = "start"
                runtime.start(directory)
                runtime.seed(identity)
                phase = "seed"
                runtime.fixture("seed", [hashlib.sha256(s.encode()).hexdigest() for s in sessions])
                if args.browser:
                    phase = "browser"
                    report["browser"] = browser(runtime, identity)
                    print(json.dumps({"browser": report["browser"]}), flush=True)
                for profile in args.profiles:
                    phase = profile
                    observer = (lambda: browser(runtime, identity)) if args.browser and profile == "soak" else None
                    result = run_recovery(runtime, sessions) if profile == "recovery" else run_load(runtime, sessions, profile, observer)
                    report["profiles"].append(result)
                    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                    print(json.dumps({"profile": profile, "passed": result["passed"],
                        "completed_jobs": result["after"]["jobs"].get("completed", 0)}), flush=True)
                    if not drained(result["after"]):
                        raise HarnessError("load_stranded_work")
            finally:
                runtime.cleanup()
                report["cleanup"] = 0
    except Exception as error:
        code = str(error) if isinstance(error, HarnessError) else "runner_failure"
        report["error"] = {"phase": phase, "code": code}
    report["passed"] = ("error" not in report and report["cleanup"] == 0
        and len(report["profiles"]) == len(args.profiles)
        and all(r["passed"] for r in report["profiles"]))
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "report": output.relative_to(ROOT).as_posix(),
                      "error": report.get("error"), "cleanup": report["cleanup"]}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
