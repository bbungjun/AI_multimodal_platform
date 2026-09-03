import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mock_auth_support as support


@pytest.mark.parametrize("project", ["", "default", "creativeops-login-preview", "ownership-verify-../",
                                    "ownership-verify-abcdef", "ownership-verify-AAAAAAAAAAAA"])
def test_project_refuses_unowned_names(project):
    with pytest.raises(support.HarnessError, match="invalid_project"):
        support.validate_project(project)


def test_project_accepts_only_fresh_namespace():
    assert support.validate_project("ownership-verify-012345abcdef") == "ownership-verify-012345abcdef"


@pytest.mark.parametrize("base", ["https://127.0.0.1:1234", "http://example.invalid:80", "http://localhost:80",
                                 "http://127.0.0.1:80@evil.invalid", "http://127.0.0.1:80/a", "http://127.0.0.1"])
def test_client_rejects_non_exact_loopback_origin(base):
    with pytest.raises(support.HarnessError):
        support.ScopedClient(base, secret=None)


@pytest.mark.parametrize("path", ["//evil.invalid/x", "http://127.0.0.1:9999/api/x", "/files/../a",
                                 "/files/%2e%2e/a", "/files/a%252fb", "/api//auth/me", "/api/a?x=1",
                                 "/files/a\\b", "/files/a\n", "/metrics"])
def test_paths_refused_before_transport(path):
    client = support.ScopedClient("http://127.0.0.1:1234", secret="a" * 43,
                                  transport=lambda _: pytest.fail("dispatch must not occur"))
    with pytest.raises(support.HarnessError):
        client.request_bytes("GET", path, expected_status=200)


def test_memory_identity_hashes_and_client_are_not_represented():
    import hashlib
    identity = support.MemoryIdentity()
    requests = []
    def transport(request):
        requests.append(request)
        return b'{}', {}, 200
    client = identity.client("http://127.0.0.1:1234", "a", transport=transport)
    client.request_json("POST", "/api/prompts/enhance", expected_status=200, payload={})
    request = requests[0]
    secret = request.get_header("Cookie").split("=", 1)[1]
    assert hashlib.sha256(secret.encode()).hexdigest() == identity.hashes()["a"]
    assert secret not in repr(identity) + repr(client) + repr(identity.hashes())
    assert request.get_header("Origin") == support.ORIGIN
    assert len(set(identity.hashes().values())) == len(support.CASES)


@pytest.mark.parametrize("header", ["Cookie", "cookie", "Authorization", "Origin", "Host"])
def test_auth_headers_cannot_be_overridden(header):
    client = support.ScopedClient("http://127.0.0.1:1234", secret="a" * 43)
    with pytest.raises(support.HarnessError, match="header_override_refused"):
        client.request_bytes("GET", "/api/auth/me", expected_status=200, headers={header: "canary"})


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 401, 500])
def test_http_errors_never_include_body_or_headers(status):
    canary = "PRIVATE_SESSION_EMAIL_PROMPT_CANARY"
    client = support.ScopedClient("http://127.0.0.1:1234", secret="a" * 43,
        transport=lambda _: (canary.encode(), {"Set-Cookie": canary}, status))
    with pytest.raises(support.HarnessError) as error:
        client.request_bytes("GET", "/api/auth/me", expected_status=200)
    assert canary not in str(error.value)


def test_transport_exception_is_sanitized():
    def fail(_):
        raise OSError("SECRET_CANARY")
    client = support.ScopedClient("http://127.0.0.1:1234", secret=None, transport=fail)
    with pytest.raises(support.HarnessError, match="http_transport_failed") as error:
        client.request_bytes("GET", "/api/auth/me", expected_status=401)
    assert "SECRET_CANARY" not in str(error.value)
    assert error.value.__suppress_context__


def test_transport_disables_proxy_and_redirect(monkeypatch):
    handlers = []
    def build(*args):
        handlers.extend(args)
        raise OSError
    monkeypatch.setattr(support, "build_opener", build)
    with pytest.raises(OSError):
        support.http_transport(None)
    assert handlers[0].proxies == {}
    with pytest.raises(support.HarnessError, match="redirect_refused"):
        handlers[1].redirect_request(None, None, 302, "", {}, "http://evil.invalid")


def test_fixture_hash_contract_matches_database_lifetimes():
    import importlib.util
    from datetime import datetime, timedelta, timezone
    path = Path(__file__).with_name("ownership_support.py")
    spec = importlib.util.spec_from_file_location("fixture_support", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hashes = support.MemoryIdentity().hashes()
    rows = module.fixture_rows(hashes, datetime.now(timezone.utc))
    assert len(rows) == 9
    assert all(row["expires"] - row["created"] == timedelta(days=7) for row in rows)
    assert all(row["created"] <= row["last_seen"] <= row["expires"] for row in rows)
    assert {row["case"] for row in rows if row["role"] == "master"} == {"master"}
    with pytest.raises(ValueError):
        module.fixture_rows({}, datetime.now(timezone.utc))


@pytest.mark.parametrize("field,value", [("project", "default"), ("host", "localhost"),
    ("database", "app"), ("provider", "vertex"), ("app_env", "production")])
def test_seed_target_guard_refuses_nonowned_or_nonmock(field, value):
    import importlib.util
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location("fixture_support", Path(__file__).with_name("ownership_support.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fields = dict(project="ownership-verify-012345abcdef", host="db",
                  database="ownership_verify_012345abcdef", provider="mock", app_env="local")
    fields[field] = value
    with pytest.raises(ValueError, match="seed_target_refused"):
        module.validate_target({"project": fields["project"], "hashes": {}},
            SimpleNamespace(host=fields["host"], database=fields["database"]), fields["provider"], fields["app_env"])
