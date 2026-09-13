#!/usr/bin/env python3
"""Run two isolated real-route browser journeys with a test-only Google adapter."""
from __future__ import annotations

import json
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time

from browser_acceptance_support import HarnessError, port_available
from mock_auth_support import OwnedRuntime, ROOT, ScopedClient, loopback_origin


FRONTEND_ORIGIN = "http://127.0.0.1:18156"
GROUPS = ("login_start", "callback_session", "profile", "logout", "replay_refusal", "relogin")


def parse_message(value: str) -> dict:
    if not value or len(value) > 4096:
        raise HarnessError("mock_oauth_protocol_invalid")
    try:
        message = json.loads(value)
    except (TypeError, ValueError):
        raise HarnessError("mock_oauth_protocol_invalid") from None
    if (
        isinstance(message, dict)
        and set(message) == {"type", "phase", "code"}
        and message.get("type") == "failed"
        and message.get("phase") in {"startup", *GROUPS}
        and message.get("code") == "mock_oauth_browser_failed"
    ):
        raise HarnessError("mock_oauth_browser_failed_" + message["phase"])
    if (
        not isinstance(message, dict)
        or set(message) != {"type", "groups", "checks", "external_requests"}
        or message.get("type") != "complete"
        or type(message.get("groups")) is not int
        or type(message.get("checks")) is not int
        or type(message.get("external_requests")) is not int
        or message["groups"] != len(GROUPS)
        or message["checks"] < 10
        or message["external_requests"] != 0
    ):
        raise HarnessError("mock_oauth_protocol_invalid")
    return message


class MockOAuthRuntime(OwnedRuntime):
    def __init__(self, env_file, *, run=None):
        super().__init__(env_file, **({} if run is None else {"run": run}))
        self.node = None

    def preflight(self):
        super().preflight()
        if not port_available(18156):
            raise HarnessError("mock_oauth_frontend_port_occupied")

    def override_text(self):
        text = super().override_text().replace('      APP_ENV: "local"', '      APP_ENV: "test"')
        start = text.index("  backend:\n")
        end = text.index("  dispatcher:\n", start)
        block = text[start:end]
        block = block.replace(
            '      AUTH_FRONTEND_ORIGIN: "http://localhost:5173"',
            f'      AUTH_FRONTEND_ORIGIN: "{FRONTEND_ORIGIN}"',
        )
        marker = "    ports: !override\n"
        if marker not in block:
            raise HarnessError("mock_oauth_override_incompatible")
        environment = "".join((
            '      AUTH_LOGIN_ENABLED: "true"\n',
            '      AUTH_COOKIE_SECURE: "false"\n',
            f"      CORS_ORIGINS: {json.dumps(json.dumps([FRONTEND_ORIGIN]))}\n",
            "    command: python -m uvicorn mock_oauth_app:app --app-dir /app/tests --host 0.0.0.0 --port 8000\n",
        ))
        block = block.replace(marker, environment + marker)
        return text[:start] + block + text[end:]

    def start(self, directory):
        """Start the owned runtime and tolerate Compose's brief created state."""
        override = Path(directory) / "compose.yml"
        override.write_text(self.override_text(), encoding="utf-8")
        self.compose = ["compose", "--project-directory", str(ROOT), "--env-file",
                        str(ROOT / ".env.example"), "--project-name", self.project,
                        "-f", str(ROOT / "docker-compose.yml"), "-f", str(override)]
        self.docker(*self.compose, "config", "--quiet")
        self.started = True
        self.docker(*self.compose, "up", "-d", "--build", "db", "redis", "backend", "dispatcher", "worker")
        self.assert_owned()
        container = self.docker(*self.compose, "ps", "--all", "-q", "backend")
        if not re.fullmatch(r"[0-9a-f]{12,64}", container):
            raise HarnessError("mock_oauth_backend_container_invalid")
        ports = None
        port_deadline = min(self.deadline, time.monotonic() + 30)
        while time.monotonic() < port_deadline:
            ports = json.loads(self.docker("container", "inspect", container,
                                          "--format", "{{json .NetworkSettings.Ports}}"))
            bindings = ports.get("8000/tcp") if isinstance(ports, dict) else None
            if isinstance(bindings, list) and len(bindings) == 1:
                break
            time.sleep(0.25)
        if (not isinstance(ports, dict) or not isinstance(bindings, list) or len(bindings) != 1
                or bindings[0].get("HostIp") != "127.0.0.1"
                or not re.fullmatch(r"[0-9]+", bindings[0].get("HostPort", ""))
                or any(value for key, value in ports.items() if key != "8000/tcp")):
            raise HarnessError("wildcard_or_multiple_bind_refused")
        self.base_url = loopback_origin("http://127.0.0.1:" + bindings[0]["HostPort"])
        anonymous = ScopedClient(self.base_url, secret=None)
        while time.monotonic() < self.deadline:
            try:
                health = anonymous.request_json("GET", "/api/health", expected_status=200)
                if health.get("ready") and health.get("vertex", {}).get("status") == "mock_provider":
                    break
            except HarnessError:
                pass
            time.sleep(0.5)
        else:
            raise HarnessError("mock_readiness_timeout")
        if self.docker(*self.compose, "exec", "-T", "redis", "redis-cli", "ping") != "PONG":
            raise HarnessError("redis_not_ready")

    def start_browser(self):
        if not self.base_url or not port_available(18156):
            raise HarnessError("mock_oauth_frontend_port_occupied")
        try:
            self.node = subprocess.Popen(
                ["node", str(ROOT / "frontend/tests/mock-oauth-browser-driver.mjs")],
                cwd=ROOT / "frontend",
                env=self.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
            )
            self.node.stdin.write(json.dumps({"type": "start", "backend_url": self.base_url,
                                               "frontend_origin": FRONTEND_ORIGIN}) + "\n")
            self.node.stdin.flush()
        except (OSError, BrokenPipeError):
            raise HarnessError("mock_oauth_browser_unavailable") from None

    def receive(self):
        if self.node is None or self.node.stdout is None:
            raise HarnessError("mock_oauth_protocol_invalid")
        incoming: queue.Queue[str] = queue.Queue(maxsize=1)
        threading.Thread(target=lambda: incoming.put(self.node.stdout.readline(4097)), daemon=True).start()
        remaining = min(180, self.deadline - time.monotonic())
        if remaining <= 0:
            raise HarnessError("cycle_deadline")
        try:
            return parse_message(incoming.get(timeout=remaining))
        except queue.Empty:
            raise HarnessError("mock_oauth_protocol_timeout") from None

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
            raise HarnessError("mock_oauth_browser_cleanup_failed") from None
        finally:
            if process.stdout:
                process.stdout.close()
        if not port_available(18156):
            raise HarnessError("mock_oauth_frontend_port_not_released")

    def cleanup(self):
        browser_error = None
        try:
            self.stop_browser()
        except HarnessError as error:
            browser_error = error
        super().cleanup()
        if browser_error:
            raise browser_error


def run_cycle(env_file: Path, cycle: int, *, runtime_factory=MockOAuthRuntime) -> dict:
    if cycle not in (1, 2):
        raise HarnessError("invalid_cycle")
    started = time.monotonic()
    runtime = runtime_factory(env_file)
    result = None
    temporary = tempfile.TemporaryDirectory(prefix="creativeops-mock-oauth-")
    try:
        runtime.preflight()
        runtime.start(temporary.name)
        runtime.start_browser()
        message = runtime.receive()
        result = {"cycle": cycle, "groups": message["groups"], "checks": message["checks"],
                  "external_requests": 0}
    finally:
        try:
            runtime.cleanup()
        finally:
            temporary.cleanup()
    result["cleanup"] = 0
    result["seconds"] = round(time.monotonic() - started, 3)
    return result


def validate_results(results: list[dict]) -> dict:
    if (
        len(results) != 2
        or [row.get("cycle") for row in results] != [1, 2]
        or any(row.get("groups") != len(GROUPS) or row.get("checks", 0) < 10
               or row.get("external_requests") != 0 or row.get("cleanup") != 0 for row in results)
    ):
        raise HarnessError("mock_oauth_acceptance_incomplete")
    return {"complete": True, "cycles": 2, "groups": len(GROUPS),
            "checks": sum(row["checks"] for row in results), "cleanup": 0, "external_requests": 0}


def main(argv=None) -> int:
    if argv if argv is not None else sys.argv[1:]:
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
