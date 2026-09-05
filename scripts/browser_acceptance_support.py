"""Owned mock browser acceptance runtime; never imported by product code."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import re
import secrets
import socket
import subprocess
import tempfile
import threading
import time

from mock_auth_support import HarnessError, MemoryIdentity, OwnedRuntime, ROOT

FRONTEND_ORIGIN = "http://127.0.0.1:18155"
GROUPS = (
    "anonymous_proxy", "user_usage", "generation_ownership", "master_commands",
    "suspension", "logout", "emergency", "mock_recovery",
)
RECEIPT = re.compile(
    r"PASS: emergency_session_revocation mode=(preview|execute) reason=operator_drill "
    r"active_before=([0-9]+) revoked=([0-9]+) active_after=([0-9]+)"
)


def port_available(port: int = 18155) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def parse_emergency_receipt(value: str) -> dict[str, int | str]:
    match = RECEIPT.fullmatch(value.strip())
    if match is None:
        raise HarnessError("emergency_receipt_invalid")
    mode, before, revoked, after = match.groups()
    numbers = {"active_before": int(before), "revoked": int(revoked), "active_after": int(after)}
    if numbers["active_before"] - numbers["revoked"] != numbers["active_after"]:
        raise HarnessError("emergency_receipt_invalid")
    return {"mode": mode, **numbers}


def parse_node_message(value: str, expected_type: str) -> dict:
    if not value or len(value) > 4096:
        raise HarnessError("browser_protocol_invalid")
    try:
        message = json.loads(value)
    except (TypeError, ValueError):
        raise HarnessError("browser_protocol_invalid") from None
    if (isinstance(message, dict) and set(message) == {"type", "phase"} and message.get("type") == "failed"
            and message.get("phase") in {"startup", "vite", *GROUPS, "browser_step"}):
        raise HarnessError("browser_failed_" + message["phase"])
    allowed = {
        "emergency_ready": {"type", "groups", "checks", "external_requests"},
        "recovery_ready": {"type", "groups", "checks", "external_requests"},
        "complete": {"type", "groups", "checks", "external_requests"},
    }
    if (expected_type not in allowed or not isinstance(message, dict)
            or set(message) != allowed[expected_type] or message.get("type") != expected_type
            or type(message.get("groups")) is not int or type(message.get("checks")) is not int
            or type(message.get("external_requests")) is not int
            or min(message["groups"], message["checks"], message["external_requests"]) < 0):
        raise HarnessError("browser_protocol_invalid")
    return message


class BrowserRuntime(OwnedRuntime):
    def __init__(self, env_file, *, run=None):
        super().__init__(env_file, **({} if run is None else {"run": run}))
        self.node = None
        self.node_stderr = None

    def preflight(self):
        super().preflight()
        if not port_available():
            raise HarnessError("frontend_port_occupied")

    def override_text(self):
        text = super().override_text()
        old = f'      AUTH_FRONTEND_ORIGIN: "{FRONTEND_ORIGIN.replace("127.0.0.1:18155", "localhost:5173")}"'
        replacement = "\n".join((
            f'      AUTH_FRONTEND_ORIGIN: "{FRONTEND_ORIGIN}"',
            f"      CORS_ORIGINS: '{json.dumps([FRONTEND_ORIGIN])}'",
            '      AUTH_LOGIN_ENABLED: "false"',
            '      AUTH_COOKIE_SECURE: "false"',
        ))
        if old not in text:
            raise HarnessError("runtime_override_incompatible")
        return text.replace(old, replacement)

    def recovery(self, raw_secrets: dict[str, str]) -> dict[str, int]:
        if set(raw_secrets) != {"a", "master"}:
            raise HarnessError("recovery_identity_invalid")
        hashes = {case: hashlib.sha256(value.encode()).hexdigest() for case, value in raw_secrets.items()}
        self.assert_owned()
        value = self.docker(
            *self.compose, "exec", "-T", "backend", "python", "tests/browser_acceptance_fixtures.py",
            input=json.dumps({"project": self.project, "hashes": hashes}),
        )
        try:
            result = json.loads(value)
        except (TypeError, ValueError):
            raise HarnessError("recovery_receipt_invalid") from None
        if (not isinstance(result, dict) or set(result) != {"recovered", "old_revoked", "active"}
                or result["recovered"] != 2 or result["active"] != 2
                or type(result["old_revoked"]) is not int or result["old_revoked"] < 2):
            raise HarnessError("recovery_receipt_invalid")
        return result

    def emergency(self, execute: bool) -> dict[str, int | str]:
        self.assert_owned()
        database = self.project.replace("-", "_")
        args = [*self.compose, "exec", "-T", "backend", "python", "-m", "app.auth.emergency",
                "--expected-database", database, "--reason", "operator_drill"]
        if execute:
            args += ["--execute", "--confirm", "REVOKE_ALL:" + database]
        return parse_emergency_receipt(self.docker(*args))

    def start_browser(self, identity: MemoryIdentity):
        if not self.base_url or not port_available():
            raise HarnessError("frontend_port_occupied")
        args = ["node", str(ROOT / "frontend/tests/browser-acceptance-driver.mjs")]
        try:
            self.node = subprocess.Popen(
                args, cwd=ROOT / "frontend", env=self.env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            )
        except OSError:
            raise HarnessError("browser_runner_unavailable") from None
        self.node_stderr = threading.Thread(target=lambda: self.node.stderr.read(), daemon=True)
        self.node_stderr.start()
        self._send({
            "type": "start", "backend_url": self.base_url, "frontend_origin": FRONTEND_ORIGIN,
            "secrets": {case: identity._secrets[case] for case in ("a", "b", "master")},
        })

    def _send(self, message: dict):
        if self.node is None or self.node.stdin is None:
            raise HarnessError("browser_protocol_invalid")
        try:
            self.node.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            self.node.stdin.flush()
        except (OSError, BrokenPipeError):
            raise HarnessError("browser_protocol_invalid") from None

    def receive(self, expected_type: str) -> dict:
        if self.node is None or self.node.stdout is None:
            raise HarnessError("browser_protocol_invalid")
        incoming: queue.Queue[str] = queue.Queue(maxsize=1)
        threading.Thread(target=lambda: incoming.put(self.node.stdout.readline(4097)), daemon=True).start()
        remaining = min(180, self.deadline - time.monotonic())
        if remaining <= 0:
            raise HarnessError("cycle_deadline")
        try:
            return parse_node_message(incoming.get(timeout=remaining), expected_type)
        except queue.Empty:
            raise HarnessError("browser_protocol_timeout") from None

    def stop_browser(self):
        process, self.node = self.node, None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            raise HarnessError("browser_cleanup_failed") from None
        finally:
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
        if not port_available():
            raise HarnessError("frontend_port_not_released")

    def cleanup(self):
        browser_error = None
        try:
            self.stop_browser()
        except HarnessError as exc:
            browser_error = exc
        super().cleanup()
        if browser_error:
            raise browser_error


def run_cycle(env_file: Path, cycle: int, *, runtime_factory=BrowserRuntime) -> dict:
    if cycle not in (1, 2):
        raise HarnessError("invalid_cycle")
    started = time.monotonic()
    runtime = runtime_factory(env_file)
    identity = MemoryIdentity()
    recovery_secrets = {case: secrets.token_urlsafe(32) for case in ("a", "master")}
    result = None
    temporary = tempfile.TemporaryDirectory(prefix="creativeops-browser-")
    try:
        runtime.preflight()
        runtime.start(temporary.name)
        runtime.seed(identity)
        runtime.start_browser(identity)
        ready = runtime.receive("emergency_ready")
        if ready != {"type": "emergency_ready", "groups": 6, "checks": ready["checks"], "external_requests": 0}:
            raise HarnessError("browser_phase_invalid")
        preview = runtime.emergency(False)
        execute = runtime.emergency(True)
        replay = runtime.emergency(True)
        if (preview["mode"] != "preview" or preview["revoked"] != 0
                or execute["mode"] != "execute" or execute["active_after"] != 0
                or execute["revoked"] < 2 or replay["revoked"] != 0):
            raise HarnessError("emergency_semantics_failed")
        runtime._send({"type": "emergency_done"})
        recovery_ready = runtime.receive("recovery_ready")
        if recovery_ready["groups"] != 7 or recovery_ready["external_requests"] != 0:
            raise HarnessError("browser_phase_invalid")
        recovery = runtime.recovery(recovery_secrets)
        runtime._send({"type": "recovery_done", "secrets": recovery_secrets})
        result = runtime.receive("complete")
        if result["groups"] != 8 or result["checks"] < 80 or result["external_requests"] != 0:
            raise HarnessError("browser_acceptance_incomplete")
        result = {"cycle": cycle, "groups": result["groups"], "checks": result["checks"],
                  "external_requests": 0, "recovered": recovery["recovered"]}
    finally:
        try:
            runtime.cleanup()
        finally:
            temporary.cleanup()
    result["cleanup"] = 0
    result["seconds"] = round(time.monotonic() - started, 3)
    return result
