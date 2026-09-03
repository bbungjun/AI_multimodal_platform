import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mock_auth_support as support


def test_admission_fixture_refuses_unowned_and_unknown_operations(monkeypatch):
    runtime = support.OwnedRuntime(support.ROOT / ".env.example")
    with pytest.raises(support.HarnessError, match="fixture_before_owned_runtime"):
        runtime.admission_fixture("counts")
    runtime.started, runtime.base_url = True, "http://127.0.0.1:1234"
    with pytest.raises(support.HarnessError, match="fixture_operation_refused"):
        runtime.admission_fixture("arbitrary_sql")


@pytest.mark.parametrize("value", ['{"email":"SECRET_CANARY"}', '{"jobs":-1}', '{"owners":"SECRET_CANARY"}', '[]'])
def test_admission_fixture_allows_only_safe_boolean_count_output(value, monkeypatch):
    runtime = support.OwnedRuntime(support.ROOT / ".env.example")
    runtime.started, runtime.base_url, runtime.compose = True, "http://127.0.0.1:1234", ["compose"]
    monkeypatch.setattr(runtime, "assert_owned", lambda: [])
    monkeypatch.setattr(runtime, "docker", lambda *a, **kw: value)
    with pytest.raises(support.HarnessError, match="unsafe_fixture_result") as error:
        runtime.admission_fixture("counts")
    assert "SECRET_CANARY" not in str(error.value)


def test_admission_counter_is_validated_before_receipt_serialization(monkeypatch, capsys):
    monkeypatch.setattr(support, "command", lambda *a, **kw: "0"*40)
    monkeypatch.setattr(support, "auth_proof", lambda *a:12)
    class Runtime:
        project = "ownership-verify-012345abcdef"
        admission_checks = "SECRET_CANARY"
        def __init__(self,*a): pass
        def preflight(self): pass
        def start(self,*a): pass
        def seed(self,*a): pass
        def cleanup(self): pass
    results = support.verify_cycles(support.ROOT / ".env.example",1,runtime_factory=Runtime,scenario=lambda *a:3)
    assert not results[0]["passed"] and results[0]["cleanup"]
    assert "SECRET_CANARY" not in capsys.readouterr().out
    assert "admission_checks" not in results[0]


def test_admission_database_helper_rejects_arbitrary_target_and_records():
    import importlib.util
    from types import SimpleNamespace
    path = support.ROOT / "backend/tests/ownership_support.py"
    spec = importlib.util.spec_from_file_location("admission_fixture_test",path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = {"project":"ownership-verify-012345abcdef","operation":"counts","records":[]}
    url = SimpleNamespace(host="db",database="ownership_verify_012345abcdef")
    module.validate_admission_target(payload,url,"mock","local")
    for change in ({"operation":"execute"},{"sql":"SELECT secret"},{"records":[{"id":"unsafe"}]}):
        with pytest.raises(ValueError):
            module.validate_admission_target(payload | change,url,"mock","local")
    with pytest.raises(ValueError):
        module.validate_admission_target(payload,SimpleNamespace(host="db",database="multimodal"),"mock","local")
    with pytest.raises(ValueError):
        module.validate_admission_target(payload,url,"vertex","local")


def test_canonical_env_only(tmp_path):
    with pytest.raises(support.HarnessError, match="only_env_example_allowed"):
        support.OwnedRuntime(tmp_path / ".env")


@pytest.mark.parametrize("endpoint", ["ssh://host", "tcp://127.0.0.1:2375", "https://host", "npipe://remote"])
def test_remote_daemon_refused_without_mutation(endpoint, monkeypatch):
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return endpoint if "inspect" in args else "test-context"
    runtime = support.OwnedRuntime(support.ROOT / ".env.example", run=run)
    with pytest.raises(support.HarnessError, match="remote_docker_refused"):
        runtime.preflight()
    assert not any("compose" in call for call in calls)


def test_collision_does_not_clean_up(monkeypatch):
    runtime = support.OwnedRuntime(support.ROOT / ".env.example")
    monkeypatch.setattr(runtime, "docker", lambda *a, **kw: "unix:///var/run/docker.sock" if "inspect" in a else "default")
    monkeypatch.setattr(runtime, "resources", lambda **kw: [("volume", "existing")])
    with pytest.raises(support.HarnessError, match="project_collision"):
        runtime.preflight()
    assert runtime.started is False
    runtime.cleanup()


def test_override_replaces_ports_and_uses_unique_database():
    runtime = support.OwnedRuntime(support.ROOT / ".env.example")
    text = runtime.override_text()
    assert 'ports: !override\n      - "127.0.0.1::8000"' in text
    assert runtime.project.replace("-", "_") in text
    assert "frontend:" not in text and "vertex.yml" not in text
    assert text.count("creativeops.verifier:") == 9
    assert "tmpfs:\n      - /data" in text


def test_seed_requires_owned_started_runtime():
    runtime = support.OwnedRuntime(support.ROOT / ".env.example")
    with pytest.raises(support.HarnessError, match="seed_before_owned_runtime"):
        runtime.seed(support.MemoryIdentity())


def test_seed_stdin_contains_only_hashes(monkeypatch):
    runtime = support.OwnedRuntime(support.ROOT / ".env.example")
    runtime.started, runtime.base_url, runtime.compose = True, "http://127.0.0.1:1234", ["compose"]
    calls = []
    monkeypatch.setattr(runtime, "assert_owned", lambda: [])
    def docker(*args, **kwargs):
        calls.append((args, kwargs))
        return "seeded"
    monkeypatch.setattr(runtime, "docker", docker)
    identity = support.MemoryIdentity()
    runtime.seed(identity)
    args, kwargs = calls[0]
    assert "tests/ownership_support.py" in args
    payload = json.loads(kwargs["input"])
    assert payload == {"project": runtime.project, "hashes": identity.hashes()}
    for raw in identity._secrets.values():
        assert raw not in repr(calls)


def test_foreign_labels_prevent_volume_removal(monkeypatch):
    runtime = support.OwnedRuntime(support.ROOT / ".env.example")
    runtime.started, runtime.compose = True, ["compose"]
    calls = []
    monkeypatch.setattr(runtime, "resources", lambda **kw: [("volume", "foreign")])
    def docker(*args, **kwargs):
        calls.append(args)
        return json.dumps({"com.docker.compose.project": runtime.project, "creativeops.verifier": "foreign"})
    monkeypatch.setattr(runtime, "docker", docker)
    with pytest.raises(support.HarnessError, match="foreign_resource_refused"):
        runtime.cleanup()
    assert not any("down" in call for call in calls)


@pytest.mark.parametrize("phase", ["preflight", "start", "seed", "auth", "scenarios", "cleanup", None])
def test_failure_receipts_and_cleanup_are_safe(phase, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(support, "command", lambda *a, **kw: "0" * 40)
    class FakeRuntime:
        project = "ownership-verify-012345abcdef"
        def __init__(self, _): pass
        def act(self, name):
            calls.append(name)
            if name == phase:
                raise RuntimeError("SECRET_CANARY@example.invalid")
        def preflight(self): self.act("preflight")
        def start(self, directory): self.act("start")
        def seed(self, identity): self.act("seed")
        def cleanup(self): self.act("cleanup")
    def auth(runtime, identity):
        runtime.act("auth")
        return 12
    def scenario(runtime, identity):
        runtime.act("scenarios")
        return 3
    monkeypatch.setattr(support, "auth_proof", auth)
    results = support.verify_cycles(support.ROOT / ".env.example", 2, runtime_factory=FakeRuntime, scenario=scenario)
    assert results[-1]["passed"] is (phase is None)
    assert "cleanup" in calls
    assert "SECRET_CANARY" not in capsys.readouterr().out
    assert len(results) == (2 if phase is None else 1)


def test_default_runtime_environment_drops_ambient_credentials(monkeypatch):
    monkeypatch.setenv("AUTH_GOOGLE_CLIENT_SECRET", "SECRET_CANARY")
    monkeypatch.setenv("DATABASE_URL", "SECRET_CANARY")
    monkeypatch.setenv("HTTPS_PROXY", "SECRET_CANARY")
    runtime = support.OwnedRuntime(support.ROOT / ".env.example")
    assert "SECRET_CANARY" not in repr(runtime.env)


def test_windows_plugin_discovery_system_path_is_preserved(monkeypatch):
    monkeypatch.setenv("ProgramFiles", "system-programs")
    runtime = support.OwnedRuntime(support.ROOT / ".env.example")
    assert any(k.upper() == "PROGRAMFILES" and v == "system-programs" for k, v in runtime.env.items())


def test_cleanup_total_deadline_is_bounded(monkeypatch):
    runtime = support.OwnedRuntime(support.ROOT / ".env.example")
    runtime.cleanup_deadline = 0
    with pytest.raises(support.HarnessError, match="cycle_deadline"):
        runtime._call(["docker"], cleanup=True)


def test_runtime_command_failure_output_is_never_exposed(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(support.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stdout="SECRET_CANARY"))
    with pytest.raises(support.HarnessError, match="command_failed") as error:
        support.command(["fake"])
    assert "SECRET_CANARY" not in str(error.value)


@pytest.mark.parametrize("bindings", [
    [{"HostIp": "0.0.0.0", "HostPort": "8000"}],
    [{"HostIp": "127.0.0.1", "HostPort": "1234"}, {"HostIp": "0.0.0.0", "HostPort": "8000"}],
    [{"HostIp": "::", "HostPort": "8000"}],
])
def test_start_rejects_wildcard_or_extra_bindings(bindings, monkeypatch, tmp_path):
    runtime = support.OwnedRuntime(support.ROOT / ".env.example")
    monkeypatch.setattr(runtime, "assert_owned", lambda: [])
    monkeypatch.setattr(runtime, "docker", lambda *a, **kw: json.dumps({"8000/tcp": bindings}) if "inspect" in a else "")
    with pytest.raises(support.HarnessError, match="wildcard_or_multiple_bind_refused"):
        runtime.start(tmp_path)
    assert runtime.started  # finally must clean partial startup
