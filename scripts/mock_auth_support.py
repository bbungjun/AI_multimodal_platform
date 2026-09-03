"""Test-only local authenticated smoke harness; never imported by the product."""
import hashlib
import json
import re
import secrets
import os
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4, uuid5, NAMESPACE_URL
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

CASES = ("a", "b", "master", "idle", "absolute", "revoked", "suspended", "synthetic", "logout")
ORIGIN = "http://localhost:5173"
ROOT = Path(__file__).resolve().parents[1]
REVISION = "0003_content_ownership"


class HarnessError(RuntimeError):
    """A bounded public failure code, never a raw exception/response."""


def validate_project(project):
    if not re.fullmatch(r"ownership-verify-[0-9a-f]{12}", project):
        raise HarnessError("invalid_project")
    return project


class MemoryIdentity:
    def __init__(self):
        self._secrets = {case: secrets.token_urlsafe(32) for case in CASES}

    def hashes(self):
        return {case: hashlib.sha256(value.encode()).hexdigest() for case, value in self._secrets.items()}

    def client(self, base_url, case, *, transport=None):
        return ScopedClient(base_url, secret=self._secrets[case], transport=transport)


def loopback_origin(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or value != f"http://127.0.0.1:{parsed.port}" + parsed.path):
            raise ValueError
    except ValueError:
        raise HarnessError("invalid_origin") from None
    return f"http://127.0.0.1:{parsed.port}"


def safe_url(base_url, path):
    base = loopback_origin(base_url)
    if (not isinstance(path, str) or not path.startswith(("/api/", "/files/"))
            or any(c in path for c in ("%", "\\", "?", "#", "\r", "\n"))
            or any(part in ("", ".", "..") for part in path.split("/")[1:])
            or not re.fullmatch(r"/[A-Za-z0-9_./-]+", path)):
        raise HarnessError("invalid_path")
    return base + path


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HarnessError("redirect_refused")


def http_transport(request):
    # A fresh opener per call is safe for concurrent duplicate requests. Never use
    # environment proxies or a CookieJar which might persist server-set cookies.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            return response.read(8 * 1024 * 1024 + 1), dict(response.headers.items()), response.status
    except HTTPError as error:
        with error:
            return error.read(8 * 1024 * 1024 + 1), dict(error.headers.items()), error.code


class ScopedClient:
    def __init__(self, base_url, *, secret, transport=None, origin=ORIGIN):
        self.base_url = loopback_origin(base_url)
        if secret is not None and not re.fullmatch(r"[A-Za-z0-9_-]{43}", secret):
            raise HarnessError("invalid_session")
        if origin != ORIGIN:
            raise HarnessError("invalid_trusted_origin")
        self._secret = secret
        self._transport = transport or http_transport

    def request_bytes(self, method, path, *, expected_status, step_name="request", payload=None, headers=None):
        url = safe_url(self.base_url, path)
        if method not in ("GET", "POST", "DELETE"):
            raise HarnessError("invalid_method")
        supplied = dict(headers or {})
        if any(key.lower() not in ("range", "accept") for key in supplied):
            raise HarnessError("header_override_refused")
        if self._secret is not None:
            supplied["Cookie"] = "creativeops_session=" + self._secret
        if method != "GET":
            supplied["Origin"] = ORIGIN
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            supplied["Content-Type"] = "application/json"
        try:
            result = self._transport(Request(url, data=data, headers=supplied, method=method))
            body, response_headers, status = result
        except Exception:
            raise HarnessError("http_transport_failed") from None
        if 300 <= status < 400:
            raise HarnessError("redirect_refused")
        allowed = (expected_status,) if isinstance(expected_status, int) else tuple(expected_status)
        if status not in allowed:
            raise HarnessError(f"unexpected_http_{status}")
        if len(body) > 8 * 1024 * 1024:
            raise HarnessError("response_too_large")
        return body, response_headers, status

    def request_json(self, method, path, **kwargs):
        body, _, _ = self.request_bytes(method, path, **kwargs)
        try:
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError
        except (ValueError, UnicodeError):
            raise HarnessError("invalid_json") from None
        return result


def command(args, *, env=None, input=None, timeout=180):
    try:
        result = subprocess.run(args, cwd=ROOT, env=env, input=input, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise HarnessError("command_unavailable_or_timeout") from None
    if result.returncode:
        raise HarnessError("command_failed")
    return result.stdout.strip()


def local_endpoint(endpoint):
    return (endpoint.startswith("unix:///") and "\n" not in endpoint
            or endpoint in ("npipe:////./pipe/dockerDesktopLinuxEngine", "npipe:////./pipe/docker_engine"))


class OwnedRuntime:
    """Owns one fresh project. It never adopts an existing target."""
    def __init__(self, env_file, *, run=command):
        if Path(env_file).resolve() != (ROOT / ".env.example").resolve():
            raise HarnessError("only_env_example_allowed")
        self.run = run
        self.project = validate_project("ownership-verify-" + uuid4().hex[:12])
        self._label = uuid4().hex
        self.context = None
        self.started = False
        self.compose = None
        self.base_url = None
        self.deadline = time.monotonic() + 360
        # Do not let ambient app credentials/configuration become Compose inputs.
        system_keys = {"PATH", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE", "TEMP", "TMP",
                       "DOCKER_CONFIG", "DOCKER_CONTEXT", "DOCKER_HOST", "COMSPEC", "PATHEXT",
                       "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "APPDATA", "LOCALAPPDATA"}
        self.env = {k: v for k, v in os.environ.items() if k.upper() in system_keys}
        self.env.update(AI_PROVIDER="mock", APP_ENV="local", GOOGLE_APPLICATION_CREDENTIALS="",
                        AUTH_GOOGLE_CLIENT_ID="", AUTH_GOOGLE_CLIENT_SECRET="", AUTH_GOOGLE_REDIRECT_URI="",
                        AUTH_FRONTEND_ORIGIN=ORIGIN, AUTH_COOKIE_SECURE="true")

    def _call(self, args, *, input=None, cleanup=False):
        deadline = getattr(self, "cleanup_deadline", self.deadline) if cleanup else self.deadline
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HarnessError("cycle_deadline")
        return self.run(args, env=self.env, input=input, timeout=min(90 if cleanup else 180, max(0.1, remaining)))

    def docker(self, *args, input=None, cleanup=False):
        prefix = ["docker"] + (["--context", self.context] if self.context else [])
        return self._call(prefix + list(args), input=input, cleanup=cleanup)

    def preflight(self):
        host = self.env.get("DOCKER_HOST")
        if host and not local_endpoint(host):
            raise HarnessError("remote_docker_refused")
        context = self.docker("context", "show")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", context):
            raise HarnessError("invalid_docker_context")
        endpoint = self.docker("context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}")
        if not local_endpoint(endpoint):
            raise HarnessError("remote_docker_refused")
        self.context = context
        self.env.pop("DOCKER_HOST", None)
        if self.resources():
            raise HarnessError("project_collision")

    def resources(self, *, cleanup=False):
        result = []
        for kind, listing in (("container", ("ps", "-aq")), ("volume", ("volume", "ls", "-q")),
                              ("network", ("network", "ls", "-q"))):
            names = self.docker(*listing, "--filter", "label=com.docker.compose.project=" + self.project,
                                cleanup=cleanup)
            result.extend((kind, name) for name in names.splitlines() if name)
        return result

    def assert_owned(self, *, cleanup=False):
        resources = self.resources(cleanup=cleanup)
        for kind, name in resources:
            selector = "{{json .Config.Labels}}" if kind == "container" else "{{json .Labels}}"
            try:
                labels = json.loads(self.docker(kind, "inspect", name, "--format", selector, cleanup=cleanup))
            except (ValueError, TypeError):
                raise HarnessError("invalid_resource_labels") from None
            if (labels.get("com.docker.compose.project") != self.project
                    or labels.get("creativeops.verifier") != self._label):
                raise HarnessError("foreign_resource_refused")
        return resources

    def override_text(self):
        database = self.project.replace("-", "_")
        url = f"postgresql+asyncpg://ownership:local_mock_only@db:5432/{database}"
        lines = ["services:"]
        for service in ("db", "redis", "migrate", "backend", "dispatcher", "worker"):
            lines += [f"  {service}:", "    labels:", f"      creativeops.verifier: {self._label}"]
            if service == "db":
                values = {"POSTGRES_USER": "ownership", "POSTGRES_PASSWORD": "local_mock_only", "POSTGRES_DB": database}
            elif service == "redis":
                values = {}
                # Avoid the image's anonymous /data volume; Redis is ephemeral.
                lines += ["    tmpfs:", "      - /data"]
            else:
                values = {"DATABASE_URL": url, "AI_PROVIDER": "mock", "APP_ENV": "local",
                          "GOOGLE_APPLICATION_CREDENTIALS": "", "AUTH_GOOGLE_CLIENT_ID": "",
                          "AUTH_GOOGLE_CLIENT_SECRET": "", "AUTH_GOOGLE_REDIRECT_URI": "",
                          "AUTH_FRONTEND_ORIGIN": ORIGIN, "AUTH_FLOW_REDIS_URL": "redis://redis:6379/1",
                          "CELERY_BROKER_URL": "redis://redis:6379/0"}
            if values:
                lines += ["    environment:"] + [f"      {k}: {json.dumps(v)}" for k, v in values.items()]
            if service == "backend":
                lines += ["    ports: !override", '      - "127.0.0.1::8000"']
        lines += ["volumes:"]
        for volume in ("pgdata", "assets"):
            lines += [f"  {volume}:", "    labels:", f"      creativeops.verifier: {self._label}"]
        lines += ["networks:", "  default:", "    labels:", f"      creativeops.verifier: {self._label}"]
        return "\n".join(lines) + "\n"

    def start(self, directory):
        override = Path(directory) / "compose.yml"
        override.write_text(self.override_text(), encoding="utf-8")
        self.compose = ["compose", "--project-directory", str(ROOT), "--env-file", str(ROOT / ".env.example"),
                        "--project-name", self.project, "-f", str(ROOT / "docker-compose.yml"), "-f", str(override)]
        self.docker(*self.compose, "config", "--quiet")
        self.started = True  # partial startup also belongs to this run
        self.docker(*self.compose, "up", "-d", "--build", "db", "redis", "backend", "dispatcher", "worker")
        self.assert_owned()
        container = self.docker(*self.compose, "ps", "-q", "backend")
        ports = json.loads(self.docker("container", "inspect", container,
                                      "--format", "{{json .NetworkSettings.Ports}}"))
        bindings = ports.get("8000/tcp") if isinstance(ports, dict) else None
        if (not isinstance(bindings, list) or len(bindings) != 1
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

    def seed(self, identity):
        if not self.started or not self.base_url:
            raise HarnessError("seed_before_owned_runtime")
        self.assert_owned()
        value = self.docker(*self.compose, "exec", "-T", "backend", "python", "tests/ownership_support.py",
                            input=json.dumps({"project": self.project, "hashes": identity.hashes()}))
        if value != "seeded":
            raise HarnessError("unexpected_seed_result")

    def cleanup(self):
        if not self.started:
            return
        self.cleanup_deadline = time.monotonic() + 90
        self.assert_owned(cleanup=True)
        self.docker(*self.compose, "down", "--volumes", "--remove-orphans", cleanup=True)
        if self.resources(cleanup=True):
            raise HarnessError("cleanup_incomplete")


def auth_proof(runtime, identity):
    for case in ("a", "b", "master"):
        result = identity.client(runtime.base_url, case).request_json("GET", "/api/auth/me", expected_status=200)
        if (result.get("id") != str(uuid5(NAMESPACE_URL, "ownership-fixture/" + case))
                or result.get("role") != ("master" if case == "master" else "user")):
            raise HarnessError("identity_mismatch")
    ScopedClient(runtime.base_url, secret=None).request_bytes("GET", "/api/auth/me", expected_status=401)
    for case in ("idle", "absolute", "revoked", "suspended", "synthetic"):
        identity.client(runtime.base_url, case).request_bytes("GET", "/api/auth/me", expected_status=401)
    # Deliberately untrusted, credential-free request tests the unchanged G3 Origin guard.
    _, _, code = http_transport(Request(runtime.base_url + "/api/auth/logout", method="POST",
                                       headers={"Origin": "http://untrusted.invalid"}))
    if code != 403:
        raise HarnessError("origin_guard_failed")
    client = identity.client(runtime.base_url, "logout")
    client.request_bytes("POST", "/api/auth/logout", expected_status=204)
    client.request_bytes("GET", "/api/auth/me", expected_status=401)
    return 12


def verify_cycles(env_file, cycles, *, runtime_factory=OwnedRuntime, scenario=None):
    if type(cycles) is not int or cycles not in (1, 2):
        raise HarnessError("invalid_cycle_count")
    results = []
    revision = command(["git", "rev-parse", "HEAD"])
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise HarnessError("invalid_code_revision")
    for _ in range(cycles):
        runtime = runtime_factory(env_file)
        receipt = dict(project=runtime.project, provider="mock", revision=REVISION, code_revision=revision, phase="preflight",
                       auth_checks=0, scenarios=0, cleanup=False, passed=False)
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="ownership-verifier-") as directory:
            try:
                runtime.preflight()
                receipt["phase"] = "start"
                runtime.start(directory)
                receipt["phase"] = "seed"
                identity = MemoryIdentity()
                runtime.seed(identity)
                receipt["phase"] = "auth"
                receipt["auth_checks"] = auth_proof(runtime, identity)
                receipt["phase"] = "scenarios"
                if scenario is None:
                    raise HarnessError("scenario_adapter_required")
                receipt["scenarios"] = scenario(runtime, identity)
                receipt["passed"] = True
            except (Exception, KeyboardInterrupt):
                # Persist only the fixed phase, never the exception or raw command output.
                receipt["passed"] = False
            finally:
                try:
                    runtime.cleanup()
                    receipt["cleanup"] = True
                except Exception:
                    receipt["cleanup"] = False
                    receipt["passed"] = False
        receipt["duration_sec"] = round(time.monotonic() - start, 2)
        results.append(receipt)
        print(json.dumps(receipt), flush=True)
        if not receipt["passed"]:
            break
    return results
