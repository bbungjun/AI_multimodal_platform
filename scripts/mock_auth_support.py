"""Test-only local authenticated smoke harness; never imported by the product."""
import hashlib
import json
import re
import secrets
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

CASES = ("a", "b", "master", "idle", "absolute", "revoked", "suspended", "synthetic", "logout")
ORIGIN = "http://localhost:5173"


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
