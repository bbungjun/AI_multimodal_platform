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
import queue
import threading
import math
from functools import wraps
from contextlib import contextmanager, nullcontext
from uuid import uuid4, uuid5, NAMESPACE_URL
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

CASES = ("a", "b", "master", "idle", "absolute", "revoked", "suspended", "synthetic", "logout")
ORIGIN = "http://localhost:5173"
ROOT = Path(__file__).resolve().parents[1]
REVISION = "0003_content_ownership"
EXECUTION_RESULTS = {
    "worker_proof": "execution_checks", "pipeline_proof": "pipeline_checks",
    "prepare_race": "prepared", "check_race": "race_checks", "lock_waiters": "lock_waiters",
    "race_completed": "race_completed", "expire_session": "expired", "check_completed": "completed_records",
}
RACE_CASES = ("create_create", "create_retry", "retry_retry")
ACCESS_RESULTS = {"prepare_metadata":"prepared", "inspect_metadata":"inspected",
    "check_read_queries":"query_checks", "clear_metadata":"cleared",
    "prepare_delete_race":"prepared", "inspect_delete_race":"race_checks", "delete_waiters":"lock_waiters"}
DELETE_CASES = ("delete_create", "delete_retry")
ACCESS_GROUPS = ("L", "D", "P", "X", "R", "C", "S", "Q")
FILE_OPS_GROUPS = ("F", "O", "V", "E")
E2E_STAGES = ("enhance", "generate", "poll", "metadata", "file", "range", "pipeline", "retry", "delete", "foreign")
ACCESS_RESULTS.update(prepare_files="prepared", clear_files="cleared")


def protocol_line(process, expected, timeout):
    """Bounded line read: even EOF or malformed output is never surfaced verbatim."""
    incoming = queue.Queue(maxsize=1)
    def read():
        try:
            incoming.put(process.stdout.readline(256))
        except Exception:
            incoming.put("")
    threading.Thread(target=read, daemon=True).start()
    try:
        line = incoming.get(timeout=max(0.01, timeout))
        if json.loads(line) != {expected: True}:
            raise ValueError
    except (queue.Empty, ValueError, TypeError):
        raise HarnessError("lock_protocol_failed") from None


class HarnessError(RuntimeError):
    """A bounded public failure code, never a raw exception/response."""


PHASES = frozenset(("preflight", "start", "seed", "file_pre_auth", "auth",
    "file_post_auth", "admission", "metadata", "smokes", "e_a", "e_b", "worker",
    "pipeline", "http_races", "expiry", "celery_completion", "validate", "cleanup"))


def safe_seconds(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise HarnessError("unsafe_timing")
    return round(value, 3)


class PhaseClock:
    """Only fixed phase names and monotonic durations can cross this Interface."""
    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.timings = {}
        self.failed_phase = None
        self.lock = threading.Lock()

    @contextmanager
    def measure(self, name):
        if name not in PHASES:
            raise HarnessError("unsafe_phase")
        start = self.clock()
        try:
            yield
        except BaseException:
            with self.lock:
                if self.failed_phase is None and name != "cleanup":
                    self.failed_phase = name
            raise
        finally:
            elapsed = safe_seconds(self.clock() - start)
            with self.lock:
                self.timings[name] = safe_seconds(self.timings.get(name, 0) + elapsed)

    def snapshot(self):
        with self.lock:
            if set(self.timings) - PHASES:
                raise HarnessError("unsafe_phase")
            return {name: safe_seconds(value) for name, value in self.timings.items()}


def phase(runtime, name):
    clock = getattr(runtime, "phase_clock", None)
    return clock.measure(name) if clock is not None else nullcontext()


def measured(name):
    def decorate(function):
        @wraps(function)
        def call(runtime, *args, **kwargs):
            with phase(runtime, name):
                return function(runtime, *args, **kwargs)
        return call
    return decorate


def failure_code(error, *, expired=False):
    if expired or (isinstance(error, HarnessError) and error.args == ("cycle_deadline",)):
        return "deadline_exceeded"
    if isinstance(error, KeyboardInterrupt):
        return "interrupted"
    return "harness_failure" if isinstance(error, HarnessError) else "unexpected_failure"


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

    def request_bytes(self, method, path, *, expected_status, step_name="request", payload=None, headers=None, query=None):
        if path == "/metrics":
            if method != "GET" or payload is not None or query is not None:
                raise HarnessError("metrics_request_refused")
            url = loopback_origin(self.base_url) + path
        else:
            url = safe_url(self.base_url, path)
        if query is not None:
            allowed = {"scope","mode","asset_kind","model","state","limit","offset"}
            if (method != "GET" or path != "/api/generations" or type(query) is not dict
                    or not set(query).issubset(allowed)):
                raise HarnessError("query_refused")
            for key,value in query.items():
                if key in ("limit","offset"):
                    if type(value) is not int or not (1 <= value <= 100 if key=="limit" else 0 <= value <= 10000):
                        raise HarnessError("query_refused")
                elif type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}",value):
                    raise HarnessError("query_refused")
            if query:
                url += "?" + urlencode(query)
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
        return self._send(Request(url, data=data, headers=supplied, method=method), expected_status)

    def file_probe(self, case, job_id, *, expected_status):
        # Closed vocabulary: never accept an arbitrary raw URL, header or method.
        from uuid import UUID
        try:
            if type(job_id) is not str or str(UUID(job_id)) != job_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise HarnessError("file_probe_refused") from None
        suffixes = {"encoded":"%6futput.bin", "encoded_slash":"%2foutput.bin",
                    "double":"%252e%252e/output.bin", "traversal":"../output.bin",
                    "dot":"./output.bin", "duplicate":"/output.bin", "head":"output.bin"}
        if type(case) is not str or case not in suffixes:
            raise HarnessError("file_probe_refused")
        url = loopback_origin(self.base_url) + "/files/" + job_id + "/" + suffixes[case]
        headers = {"Cookie":"creativeops_session="+self._secret} if self._secret else {}
        return self._send(Request(url,headers=headers,method="HEAD" if case=="head" else "GET"),expected_status)

    def _send(self, request, expected_status):
        try:
            result = self._transport(request)
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

    def request_json(self, method, path, *, expected_type=dict, **kwargs):
        if expected_type not in (dict,list):
            raise HarnessError("invalid_json_type")
        body, _, _ = self.request_bytes(method, path, **kwargs)
        try:
            result = json.loads(body)
            if not isinstance(result, expected_type) or (expected_type is list and any(type(row) is not dict for row in result)):
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

    def admission_fixture(self, operation, records=None):
        if not self.started or not self.base_url:
            raise HarnessError("fixture_before_owned_runtime")
        if operation not in {"prepare", "counts", "assert_rows", "arm_commit_failure", "disarm_commit_failure", "clear"}:
            raise HarnessError("fixture_operation_refused")
        self.assert_owned()
        value = self.docker(*self.compose, "exec", "-T", "backend", "python", "tests/ownership_support.py",
            input=json.dumps({"project": self.project, "operation": operation, "records": records or []}))
        result = json.loads(value)
        fields = {"prepared", "completed", "rows_checked", "owners", "outbox", "lineage",
                  "jobs", "assets", "prompt_enhancements", "outbox_events"}
        if (not isinstance(result, dict) or not result or not set(result).issubset(fields)
                or any(type(v) not in (bool, int) or v < 0 for v in result.values())):
            raise HarnessError("unsafe_fixture_result")
        return result

    def execution_payload(self, operation, case="", records=None):
        if not self.started or not self.base_url:
            raise HarnessError("fixture_before_owned_runtime")
        if operation not in {*EXECUTION_RESULTS, "hold_source"}:
            raise HarnessError("fixture_operation_refused")
        race = operation in {"prepare_race", "check_race", "lock_waiters", "race_completed", "hold_source"}
        records = [] if records is None else records
        if case not in (RACE_CASES if race else ("",)) or type(records) is not list or len(records) > 2:
            raise HarnessError("fixture_input_refused")
        if operation != "check_completed" and records:
            raise HarnessError("fixture_input_refused")
        from uuid import UUID
        try:
            for record in records:
                if (not isinstance(record, dict) or set(record) != {"kind", "id"}
                        or record["kind"] not in ("pipeline", "expiry")):
                    raise ValueError
                UUID(record["id"])
        except (ValueError, TypeError, AttributeError):
            raise HarnessError("fixture_input_refused") from None
        return json.dumps(dict(project=self.project, operation=operation, case=case, records=records)) + "\n"

    def execution_fixture(self, operation, case="", records=None):
        payload = self.execution_payload(operation, case, records)
        if operation not in EXECUTION_RESULTS:
            raise HarnessError("fixture_operation_refused")
        self.assert_owned()
        value = self.docker(*self.compose, "exec", "-T", "backend", "python", "tests/ownership_execution_support.py",
                            input=payload)
        field = EXECUTION_RESULTS[operation]
        try:
            result = json.loads(value)
            expected_type = bool if field in {"prepared", "expired"} else int
            if (not isinstance(result, dict) or set(result) != {field}
                    or type(result[field]) is not expected_type or result[field] < 0):
                raise ValueError
        except (ValueError, TypeError):
            raise HarnessError("unsafe_execution_result") from None
        return result

    def access_payload(self, operation, case="", records=None):
        if not self.started or not self.base_url:
            raise HarnessError("fixture_before_owned_runtime")
        race = operation in {"prepare_delete_race","inspect_delete_race","hold_delete_source","delete_waiters"}
        if operation not in {*ACCESS_RESULTS,"hold_delete_source"} or case not in (DELETE_CASES if race else ("",)):
            raise HarnessError("access_operation_refused")
        records = [] if records is None else records
        if type(records) is not list or len(records)>16 or (records and operation != "inspect_delete_race"):
            raise HarnessError("access_records_refused")
        from uuid import UUID
        try:
            for record in records:
                if type(record) is not dict or set(record)!={"kind","id"} or record["kind"]!="admitted":
                    raise ValueError
                UUID(record["id"])
        except (ValueError,TypeError,AttributeError):
            raise HarnessError("access_records_refused") from None
        return json.dumps(dict(project=self.project,access_operation=operation,case=case,records=records))+"\n"

    def access_fixture(self, operation, case="", records=None):
        payload=self.access_payload(operation,case,records)
        if operation not in ACCESS_RESULTS:
            raise HarnessError("access_operation_refused")
        self.assert_owned()
        value=self.docker(*self.compose,"exec","-T","backend","python","tests/ownership_support.py",input=payload)
        field=ACCESS_RESULTS[operation]
        try:
            result=json.loads(value)
            expected=bool if field in ("prepared","inspected","cleared") else int
            if type(result) is not dict or set(result)!={field} or type(result[field]) is not expected or result[field]<0:
                raise ValueError
        except (ValueError,TypeError):
            raise HarnessError("unsafe_access_result") from None
        return result

    def observe_delete_waiters(self, case):
        previous=self.deadline
        self.deadline=min(previous,time.monotonic()+5)
        try:
            while time.monotonic()<self.deadline:
                if self.access_fixture("delete_waiters",case)=={"lock_waiters":2} and time.monotonic()<self.deadline:
                    return
            raise HarnessError("delete_lock_overlap_missing")
        finally:
            self.deadline=previous

    def delete_source_lock(self, case):
        return self._source_lock(case,access=True)

    def observe_source_waiters(self, case):
        # Clamp every label check and command to the same five-second window.
        previous_deadline = self.deadline
        self.deadline = min(previous_deadline, time.monotonic() + 5)
        try:
            while time.monotonic() < self.deadline:
                result = self.execution_fixture("lock_waiters",case)
                if result == {"lock_waiters":2} and time.monotonic() <= self.deadline:
                    return
            raise HarnessError("source_lock_overlap_missing")
        finally:
            self.deadline = previous_deadline

    def source_lock(self, case):
        return self._source_lock(case,access=False)

    @contextmanager
    def _source_lock(self, case, *, access):
        payload = self.access_payload("hold_delete_source",case) if access else self.execution_payload("hold_source", case)
        self.assert_owned()
        if self.deadline - time.monotonic() < 25:
            raise HarnessError("cycle_deadline")
        args = ["docker", "--context", self.context, *self.compose, "exec", "-T", "backend",
                "python", "tests/ownership_support.py" if access else "tests/ownership_execution_support.py"]
        process = None
        try:
            process = subprocess.Popen(args, cwd=ROOT, env=self.env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       text=True, encoding="utf-8")
            process.stdin.write(payload)
            process.stdin.flush()
            protocol_line(process, "locked", 5)
            yield
            process.stdin.write('{"release":true}\n')
            process.stdin.flush()
            protocol_line(process, "released", 5)
            if process.wait(timeout=5):
                raise HarnessError("lock_helper_failed")
        except (OSError, subprocess.TimeoutExpired):
            raise HarnessError("lock_helper_failed") from None
        finally:
            if process is not None:
                try:
                    process.stdin.close()  # EOF asks the in-container holder to rollback.
                except OSError:
                    pass
                try:
                    process.wait(timeout=22)  # holder self-timeout is20; launcher death is NOT proof of cleanup.
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    raise HarnessError("lock_helper_cleanup_failed") from None
                finally:
                    process.stdout.close()


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
    client = getattr(runtime,"file_logout_client",None) or identity.client(runtime.base_url, "logout")
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
        start = time.monotonic()
        runtime = runtime_factory(env_file)
        runtime.phase_clock = PhaseClock()
        work_deadline = min(getattr(runtime, "deadline", start + 360), start + 360)
        receipt = dict(project=runtime.project, provider="mock", revision=REVISION, code_revision=revision, phase="preflight",
                       auth_checks=0, scenarios=0, cleanup=False, passed=False,
                       failure_code="none", cleanup_failure_code="none")
        with tempfile.TemporaryDirectory(prefix="ownership-verifier-") as directory:
            try:
                with phase(runtime, "preflight"):
                    runtime.preflight()
                receipt["phase"] = "start"
                with phase(runtime, "start"):
                    runtime.start(directory)
                receipt["phase"] = "seed"
                identity = MemoryIdentity()
                with phase(runtime, "seed"):
                    runtime.seed(identity)
                file_ops = bool(getattr(scenario,"requires_file_ops",False))
                if file_ops:
                    from verify_ownership import file_ops_before_auth
                    with phase(runtime, "file_pre_auth"):
                        file_ops_before_auth(runtime,identity)
                receipt["phase"] = "auth"
                with phase(runtime, "auth"):
                    receipt["auth_checks"] = auth_proof(runtime, identity)
                if file_ops:
                    from verify_ownership import file_ops_after_auth
                    with phase(runtime, "file_post_auth"):
                        file_ops_after_auth(runtime,identity)
                receipt["phase"] = "scenarios"
                if scenario is None:
                    raise HarnessError("scenario_adapter_required")
                receipt["scenarios"] = scenario(runtime, identity)
                admission_checks = getattr(runtime, "admission_checks", 0)
                if type(admission_checks) is not int or admission_checks < 0:
                    raise HarnessError("unsafe_admission_receipt")
                receipt["admission_checks"] = admission_checks
                for field in ("execution_checks", "pipeline_checks", "race_checks", "expiry_checks"):
                    value = getattr(runtime, field, 0)
                    if type(value) is not int or value < 0:
                        raise HarnessError("unsafe_execution_receipt")
                    receipt[field] = value
                if scenario is not None and getattr(scenario,"requires_access",False):
                    groups=getattr(runtime,"access_completed",None)
                    checks=getattr(runtime,"access_checks",None)
                    races=getattr(runtime,"delete_race_checks",None)
                    if (type(groups) is not dict or set(groups)!=set(ACCESS_GROUPS)
                            or any(value is not True for value in groups.values())
                            or type(checks) is not int or checks<=0 or type(races) is not int or races!=2):
                        raise HarnessError("unsafe_access_receipt")
                    receipt.update(access_groups=8,access_checks=checks,delete_race_checks=races)
                if file_ops:
                    validate_file_ops_receipt(runtime)
                    receipt.update(file_ops_groups=4,file_ops_checks=runtime.file_ops_checks,e2e_actors=2)
                if time.monotonic() > work_deadline:
                    raise HarnessError("cycle_deadline")
                receipt["passed"] = True
            except (Exception, KeyboardInterrupt) as error:
                receipt["passed"] = False
                receipt["failure_code"] = failure_code(error, expired=time.monotonic() > work_deadline)
            finally:
                work_end = time.monotonic()
                receipt["work_sec"] = safe_seconds(work_end - start)
                try:
                    with phase(runtime, "cleanup"):
                        runtime.cleanup()
                    if time.monotonic() - work_end > 90:
                        raise HarnessError("cycle_deadline")
                    receipt["cleanup"] = True
                except (Exception, KeyboardInterrupt):
                    receipt["cleanup"] = False
                    receipt["passed"] = False
                    receipt["cleanup_failure_code"] = "cleanup_failed"
                receipt["cleanup_sec"] = safe_seconds(time.monotonic() - work_end)
        receipt["duration_sec"] = safe_seconds(time.monotonic() - start)
        try:
            receipt["phase_seconds"] = runtime.phase_clock.snapshot()
            if runtime.phase_clock.failed_phase is not None:
                receipt["phase"] = runtime.phase_clock.failed_phase
        except HarnessError:
            receipt.update(passed=False, failure_code="invalid_receipt")
        results.append(receipt)
        print(json.dumps(receipt), flush=True)
        if not receipt["passed"]:
            break
    return results


def validate_file_ops_receipt(runtime):
    groups=getattr(runtime,"file_ops_completed",None)
    stages=getattr(runtime,"e2e_completed",None)
    count=getattr(runtime,"file_ops_checks",None)
    if (type(groups) is not dict or set(groups)!=set(FILE_OPS_GROUPS)
            or any(value is not True for value in groups.values())
            or type(count) is not int or count<=0 or type(stages) is not dict or set(stages)!={"a","b"}):
        raise HarnessError("unsafe_file_ops_receipt")
    for values in stages.values():
        if type(values) is not dict or set(values)!=set(E2E_STAGES) or any(v is not True for v in values.values()):
            raise HarnessError("unsafe_file_ops_receipt")
