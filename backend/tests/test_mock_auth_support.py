import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mock_auth_support as support


def test_access_structured_list_query_and_array_response():
    observed=[]
    def transport(request):
        observed.append(request.full_url)
        return b'[{"state":"completed"}]',{},200
    client=support.ScopedClient("http://127.0.0.1:1234",secret=None,transport=transport)
    rows=client.request_json("GET","/api/generations",query={"scope":"mine","limit":20,"offset":2},expected_type=list,expected_status=200)
    assert rows==[{"state":"completed"}]
    assert observed==["http://127.0.0.1:1234/api/generations?scope=mine&limit=20&offset=2"]


@pytest.mark.parametrize("query", [{"limit":True},{"limit":101},{"offset":-1},{"offset":10001},
    {"unknown":"x"},{"model":"a&scope=all"},{"scope":"x\r\n"},{"model":"x"*129},[("scope","all")]])
def test_access_query_refuses_unbounded_or_unstructured_values(query):
    client=support.ScopedClient("http://127.0.0.1:1234",secret=None,transport=lambda _:pytest.fail("must not send"))
    with pytest.raises(support.HarnessError):
        client.request_bytes("GET","/api/generations",query=query,expected_status=200)


@pytest.mark.parametrize("method,path", [("POST","/api/generations"),("GET","/api/auth/me"),("GET","/metrics")])
def test_access_query_cannot_expand_transport_routes(method,path):
    client=support.ScopedClient("http://127.0.0.1:1234",secret=None,transport=lambda _:pytest.fail("must not send"))
    with pytest.raises(support.HarnessError):
        client.request_bytes(method,path,query={"scope":"all"},expected_status=200)


@pytest.mark.parametrize("data,kind", [(b'[]',dict),(b'{}',list),(b'[1]',list),(b'["SECRET_CANARY"]',list)])
def test_access_array_type_is_explicit_and_validated(data,kind):
    client=support.ScopedClient("http://127.0.0.1:1234",secret=None,transport=lambda _:(data,{},200))
    with pytest.raises(support.HarnessError) as exc:
        client.request_json("GET","/api/generations",expected_status=200,expected_type=kind)
    assert "SECRET_CANARY" not in str(exc.value)


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
                                 "/files/a\\b", "/files/a\n", "/metrics/"])
def test_paths_refused_before_transport(path):
    client = support.ScopedClient("http://127.0.0.1:1234", secret="a" * 43,
                                  transport=lambda _: pytest.fail("dispatch must not occur"))
    with pytest.raises(support.HarnessError):
        client.request_bytes("GET", path, expected_status=200)


def test_file_ops_exact_metrics_get_only():
    requests=[]
    client=support.ScopedClient("http://127.0.0.1:1234",secret="a"*43,
        transport=lambda request:(requests.append(request) or (b"metrics",{},200)))
    assert client.request_bytes("GET","/metrics",expected_status=200)[0]==b"metrics"
    assert requests[0].full_url=="http://127.0.0.1:1234/metrics"
    with pytest.raises(support.HarnessError): support.safe_url(client.base_url,"/metrics")
    for method,options in (("POST",{}),("HEAD",{}),("GET",{"payload":{}}),("GET",{"query":{}})):
        with pytest.raises(support.HarnessError): client.request_bytes(method,"/metrics",expected_status=200,**options)
    assert len(requests)==1


@pytest.mark.parametrize("case",["encoded","encoded_slash","double","traversal","dot","duplicate","head"])
def test_file_ops_fixed_probe_stays_on_loopback(case):
    requests=[]
    client=support.ScopedClient("http://127.0.0.1:1234",secret="a"*43,
        transport=lambda request:(requests.append(request) or (b"",{},405 if case=="head" else 404)))
    client.file_probe(case,"00000000-0000-0000-0000-000000000123",expected_status=(404,405))
    assert requests[0].full_url.startswith("http://127.0.0.1:1234/files/00000000-0000-0000-0000-000000000123/")
    assert requests[0].method == ("HEAD" if case=="head" else "GET")
    assert requests[0].get_header("Cookie")=="creativeops_session="+"a"*43


@pytest.mark.parametrize("case,job",[("https://evil.invalid","00000000-0000-0000-0000-000000000123"),
    ("head","../a"),("head","00000000-0000-0000-0000-000000000123%0a"),(None,None)])
def test_file_ops_probe_refuses_arbitrary_input(case,job):
    client=support.ScopedClient("http://127.0.0.1:1234",secret=None,transport=lambda _:pytest.fail("no send"))
    with pytest.raises(support.HarnessError): client.file_probe(case,job,expected_status=404)


@pytest.mark.parametrize("kind",["redirect","exception","oversize"])
def test_file_ops_probe_shared_response_guards(kind):
    def transport(request):
        if kind=="exception": raise RuntimeError("SECRET_CANARY")
        return (b"x"*(8*1024*1024+1) if kind=="oversize" else b"",{},302 if kind=="redirect" else 200)
    client=support.ScopedClient("http://127.0.0.1:1234",secret=None,transport=transport)
    with pytest.raises(support.HarnessError) as exc:
        client.file_probe("head","00000000-0000-0000-0000-000000000123",expected_status=200)
    assert "SECRET_CANARY" not in str(exc.value)


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
@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), "SECRET_CANARY"])
def test_v2_timing_refuses_unsafe_values(value):
    from mock_auth_support import HarnessError, safe_seconds
    with pytest.raises(HarnessError, match="unsafe_timing"):
        safe_seconds(value)


def test_v2_phase_clock_fixed_names_and_failed_duration():
    from mock_auth_support import PhaseClock, HarnessError
    values = iter((1.0, 3.5))
    clock = PhaseClock(clock=lambda: next(values))
    with pytest.raises(ValueError):
        with clock.measure("auth"):
            raise ValueError("SECRET_CANARY")
    assert clock.failed_phase == "auth"
    assert clock.snapshot() == {"auth": 2.5}
    with pytest.raises(HarnessError, match="unsafe_phase"):
        with clock.measure("SECRET_CANARY"):
            pass
    clock.timings["SECRET_CANARY"] = 0
    with pytest.raises(HarnessError, match="unsafe_phase"):
        clock.snapshot()


@pytest.mark.parametrize("error,expired,expected", [
    (RuntimeError("SECRET_CANARY"), False, "unexpected_failure"),
    (KeyboardInterrupt("SECRET_CANARY"), False, "interrupted"),
    (RuntimeError("SECRET_CANARY"), True, "deadline_exceeded"),
])
def test_v2_failure_codes_never_use_exception_payload(error, expired, expected):
    from mock_auth_support import failure_code, HarnessError
    assert failure_code(error, expired=expired) == expected
    assert failure_code(HarnessError("SECRET_CANARY")) == "harness_failure"
    assert failure_code(HarnessError("cycle_deadline")) == "deadline_exceeded"


@pytest.mark.parametrize("late", [False, True])
def test_v2_client_stops_before_or_after_cycle_deadline(late, monkeypatch):
    now, calls = [11 if not late else 9], []
    monkeypatch.setattr(support.time, "monotonic", lambda: now[0])
    def transport(request):
        calls.append(True)
        now[0] = 11
        return b"", {}, 200
    client = support.ScopedClient("http://127.0.0.1:1234", secret=None, transport=transport, deadline=10)
    with pytest.raises(support.HarnessError, match="cycle_deadline"):
        client.request_bytes("GET", "/api/health", expected_status=200)
    assert len(calls) == int(late)


def test_v2_default_transport_is_clamped_to_remaining_time(monkeypatch):
    monkeypatch.setattr(support.time, "monotonic", lambda: 9)
    seen = []
    def transport(request, *, timeout):
        seen.append(timeout)
        return b"", {}, 200
    monkeypatch.setattr(support, "http_transport", transport)
    client = support.ScopedClient("http://127.0.0.1:1234", secret=None, deadline=10)
    client.request_bytes("GET", "/api/health", expected_status=200)
    assert seen == [1]
