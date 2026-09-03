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


@pytest.mark.parametrize("field", ["execution_checks", "pipeline_checks", "race_checks", "expiry_checks"])
@pytest.mark.parametrize("value", ["SECRET_CANARY", -1, True])
def test_execution_receipt_canary(field, value, monkeypatch, capsys):
    monkeypatch.setattr(support,"command",lambda *a,**kw:"0"*40)
    monkeypatch.setattr(support,"auth_proof",lambda *a:12)
    class Runtime:
        project = "ownership-verify-012345abcdef"
        def __init__(self,*a): setattr(self,field,value)
        def preflight(self): pass
        def start(self,*a): pass
        def seed(self,*a): pass
        def cleanup(self): pass
    result = support.verify_cycles(support.ROOT/".env.example",1,runtime_factory=Runtime,scenario=lambda *a:3)[0]
    assert not result["passed"] and result["cleanup"] and field not in result
    assert "SECRET_CANARY" not in capsys.readouterr().out


@pytest.mark.parametrize("output", ['{"execution_checks":"SECRET_CANARY"}', 'SECRET_CANARY',
                                  '{"execution_checks":true}', '{"execution_checks":-1}', '{"email":"SECRET_CANARY"}'])
def test_execution_output_guard(output, monkeypatch):
    runtime = support.OwnedRuntime(support.ROOT/".env.example")
    runtime.started, runtime.base_url, runtime.compose = True,"http://127.0.0.1:1234",["compose"]
    monkeypatch.setattr(runtime,"assert_owned",lambda:[])
    monkeypatch.setattr(runtime,"docker",lambda *a,**kw:output)
    with pytest.raises(support.HarnessError,match="unsafe_execution_result") as error:
        runtime.execution_fixture("worker_proof")
    assert "SECRET_CANARY" not in str(error.value)


def test_execution_inputs_fixed_before_any_docker_command(monkeypatch):
    runtime = support.OwnedRuntime(support.ROOT/".env.example")
    with pytest.raises(support.HarnessError): runtime.execution_fixture("worker_proof")
    runtime.started, runtime.base_url = True,"http://127.0.0.1:1234"
    monkeypatch.setattr(runtime,"assert_owned",lambda:pytest.fail("must not reach Docker"))
    for args in [("sql",), ("hold_source","create_create"), ("prepare_race","arbitrary"),
                 ("worker_proof","",[{}]), ("check_completed","",[{"kind":"pipeline","id":"bad"}]),
                 ("check_completed","",[{}]*3)]:
        with pytest.raises(support.HarnessError): runtime.execution_fixture(*args)


def execution_helper():
    import importlib.util
    path = support.ROOT/"backend/tests/ownership_execution_support.py"
    sys.path.insert(0,str(path.parent))
    spec = importlib.util.spec_from_file_location("execution_fixture_test",path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_execution_helper_target_and_payload_guards():
    from types import SimpleNamespace
    module = execution_helper()
    payload = dict(project="ownership-verify-012345abcdef",operation="worker_proof",case="",records=[])
    url = SimpleNamespace(host="db",database="ownership_verify_012345abcdef")
    module.validate_payload(payload,url,"mock","local")
    for change in [{"operation":"sql"},{"case":"arbitrary"},{"sql":"secret"},
                   {"records":[{}]}, {"operation":"hold_source"}, {"records":[{}]*3},
                   {"operation":"check_completed","records":[{"kind":"sql","id":"bad"}]}]:
        with pytest.raises(ValueError): module.validate_payload(payload|change,url,"mock","local")
    for target,provider,env in [(SimpleNamespace(host="remote",database=url.database),"mock","local"),
            (SimpleNamespace(host="db",database="multimodal"),"mock","local"),(url,"vertex","local"),(url,"mock","prod")]:
        with pytest.raises(ValueError): module.validate_payload(payload,target,provider,env)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["head","identities"])
async def test_execution_inventory_rejects_wrong_head_or_identity(bad):
    import ownership_support
    from types import SimpleNamespace
    class Session:
        async def scalar(self,*a): return "stale" if bad == "head" else support.REVISION
        async def scalars(self,*a): return SimpleNamespace(all=lambda:[])
    with pytest.raises(ValueError): await ownership_support.validate_fixture_inventory(Session())


@pytest.mark.parametrize("line", ["", "SECRET_CANARY\n", '{"locked":false}\n', '{"locked":true,"extra":1}\n'])
def test_lock_protocol_eof_or_unsafe_output(line):
    from io import StringIO
    from types import SimpleNamespace
    with pytest.raises(support.HarnessError,match="lock_protocol_failed") as error:
        support.protocol_line(SimpleNamespace(stdout=StringIO(line)),"locked",0.1)
    assert "SECRET_CANARY" not in str(error.value)


def test_lock_protocol_timeout(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(support.threading,"Thread",lambda **kw:SimpleNamespace(start=lambda:None))
    with pytest.raises(support.HarnessError,match="lock_protocol_failed"):
        support.protocol_line(SimpleNamespace(),"locked",0.01)


@pytest.mark.parametrize("failure", [None,"body","broken_pipe","timeout","eof"])
@pytest.mark.parametrize("access", [False,True])
def test_source_lock_reaps_its_fixed_helper(failure,access,monkeypatch):
    from io import StringIO
    runtime = support.OwnedRuntime(support.ROOT/".env.example")
    runtime.started,runtime.base_url,runtime.compose,runtime.context = True,"http://127.0.0.1:1234",["compose"],"local"
    monkeypatch.setattr(runtime,"assert_owned",lambda:[])
    class Input(StringIO):
        def flush(self):
            if failure == "broken_pipe": raise BrokenPipeError("SECRET_CANARY")
    class Process:
        stdin = Input()
        stdout = StringIO('' if failure == "eof" else '{"locked":true}\n{"released":true}\n')
        waited = 0
        killed = False
        def wait(self,timeout):
            self.waited += 1
            if failure == "timeout" and self.waited <= 2: raise support.subprocess.TimeoutExpired("fixed",timeout)
            return 0
        def kill(self): self.killed = True
    process = Process()
    def popen(args,**kw):
        assert args[-1] == ("tests/ownership_support.py" if access else "tests/ownership_execution_support.py")
        assert args[0:3] == ["docker","--context","local"]
        assert kw["stderr"] is support.subprocess.DEVNULL
        return process
    monkeypatch.setattr(support.subprocess,"Popen",popen)
    def run():
        with (runtime.delete_source_lock("delete_create") if access else runtime.source_lock("create_create")):
            if failure == "body": raise support.HarnessError("test_body")
    if failure:
        with pytest.raises(support.HarnessError) as error: run()
        assert "SECRET_CANARY" not in str(error.value)
    else:
        run()
    assert process.waited and process.stdin.closed and process.stdout.closed
    assert process.killed is (failure == "timeout")


def access_helper():
    import importlib.util
    spec=importlib.util.spec_from_file_location("access_helper_test",support.ROOT/"backend/tests/ownership_support.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("change", [{"project":"default"},{"access_operation":"sql"},{"case":"wrong"},
    {"records":[{"kind":"admitted","id":"not-uuid"}]},{"sql":"SECRET_CANARY"}])
def test_access_fixture_payload_refusal(change):
    from types import SimpleNamespace
    module=access_helper()
    payload=dict(project="ownership-verify-012345abcdef",access_operation="prepare_metadata",case="",records=[])
    with pytest.raises((ValueError,TypeError)):
        module.validate_access_payload(payload|change,SimpleNamespace(host="db",database="ownership_verify_012345abcdef"),"mock","local")


@pytest.mark.parametrize("host,database,provider,app_env", [("remote","ownership_verify_012345abcdef","mock","local"),
    ("db","multimodal","mock","local"),("db","ownership_verify_012345abcdef","vertex","local"),
    ("db","ownership_verify_012345abcdef","mock","production")])
def test_access_fixture_never_targets_other_environment(host,database,provider,app_env):
    from types import SimpleNamespace
    payload=dict(project="ownership-verify-012345abcdef",access_operation="prepare_metadata",case="",records=[])
    with pytest.raises(ValueError):
        access_helper().validate_access_payload(payload,SimpleNamespace(host=host,database=database),provider,app_env)


@pytest.mark.parametrize("value", ['{"email":"SECRET_CANARY"}','{"prepared":1}','{"prepared":true,"id":"SECRET_CANARY"}',
    '[]','{"prepared":-1}'])
def test_access_fixture_output_safety(value,monkeypatch):
    runtime=support.OwnedRuntime(support.ROOT/".env.example")
    runtime.started,runtime.base_url,runtime.compose=True,"http://127.0.0.1:1234",["compose"]
    monkeypatch.setattr(runtime,"assert_owned",lambda:[])
    monkeypatch.setattr(runtime,"docker",lambda *a,**kw:value)
    with pytest.raises(support.HarnessError) as exc:
        runtime.access_fixture("prepare_metadata")
    assert "SECRET_CANARY" not in str(exc.value)


@pytest.mark.parametrize("bad", ["missing","zero","negative","type","group","race",None])
def test_access_receipt_requires_all_groups_and_safe_counts(bad,monkeypatch,capsys):
    monkeypatch.setattr(support,"command",lambda *a,**kw:"0"*40)
    monkeypatch.setattr(support,"auth_proof",lambda *a:12)
    class Runtime:
        project="ownership-verify-012345abcdef"
        def __init__(self,*a): pass
        def preflight(self): pass
        def start(self,*a): pass
        def seed(self,*a): pass
        def cleanup(self): pass
    def scenario(runtime,identity):
        runtime.access_completed=dict.fromkeys(support.ACCESS_GROUPS,True)
        runtime.access_checks={"zero":0,"negative":-1,"type":"SECRET_CANARY"}.get(bad,10)
        runtime.delete_race_checks=1 if bad=="race" else 2
        if bad=="missing": del runtime.access_completed["Q"]
        if bad=="group": runtime.access_completed["Q"]=1
        return 3
    scenario.requires_access=True
    receipt=support.verify_cycles(support.ROOT/".env.example",1,runtime_factory=Runtime,scenario=scenario)[0]
    assert receipt["passed"] is (bad is None)
    assert receipt["cleanup"] and "SECRET_CANARY" not in capsys.readouterr().out


def test_access_canonical_scenario_requires_proof():
    import verify_ownership
    assert verify_ownership.scenarios.requires_access is True
    assert verify_ownership.scenarios.suite == "ownership"
    assert not getattr(verify_ownership.scenarios, "requires_file_ops", False)
    assert verify_ownership.file_ops_scenarios.requires_file_ops is True
    assert verify_ownership.file_ops_scenarios.suite == "file-ops"
    assert not getattr(verify_ownership.file_ops_scenarios, "requires_access", False)


@pytest.mark.parametrize("bad",[None,"missing_group","false_group","extra_group","bool_count","zero_count",
    "missing_actor","missing_stage","false_stage","nonbool_stage","secret"])
def test_file_ops_receipt_requires_exact_groups_and_both_actor_stages(bad):
    from types import SimpleNamespace
    runtime=SimpleNamespace(file_ops_completed=dict.fromkeys(support.FILE_OPS_GROUPS,True),
        file_ops_checks=42,e2e_completed={case:dict.fromkeys(support.E2E_STAGES,True) for case in ("a","b")})
    if bad=="missing_group": del runtime.file_ops_completed["V"]
    if bad=="false_group": runtime.file_ops_completed["F"]=False
    if bad=="extra_group": runtime.file_ops_completed["SECRET_CANARY"]=True
    if bad=="bool_count": runtime.file_ops_checks=True
    if bad=="zero_count": runtime.file_ops_checks=0
    if bad=="missing_actor": del runtime.e2e_completed["b"]
    if bad=="missing_stage": del runtime.e2e_completed["a"]["range"]
    if bad=="false_stage": runtime.e2e_completed["b"]["pipeline"]=False
    if bad=="nonbool_stage": runtime.e2e_completed["a"]["retry"]=1
    if bad=="secret": runtime.file_ops_checks="SECRET_CANARY"
    if bad is None:
        support.validate_file_ops_receipt(runtime)
    else:
        with pytest.raises(support.HarnessError) as exc: support.validate_file_ops_receipt(runtime)
        assert "SECRET_CANARY" not in str(exc.value)


@pytest.mark.parametrize("operation",["prepare_files","clear_files"])
def test_file_ops_fixture_guards_and_exact_namespace(operation):
    from types import SimpleNamespace
    helper=access_helper()
    payload=dict(project="ownership-verify-012345abcdef",access_operation=operation,case="",records=[])
    url=SimpleNamespace(host="db",database="ownership_verify_012345abcdef")
    helper.validate_access_payload(payload,url,"mock","local")
    for update in ({"records":[{"kind":"admitted","id":"00000000-0000-0000-0000-000000000123"}]},
                   {"case":"a"},{"project":"creativeops-login-preview"},{"sql":"SECRET_CANARY"}):
        with pytest.raises(ValueError): helper.validate_access_payload(payload|update,url,"mock","local")
    for provider,env in (("vertex","local"),("mock","production")):
        with pytest.raises(ValueError): helper.validate_access_payload(payload,url,provider,env)
    assert str(helper.file_id("a","job"))!=str(helper.access_id("a","job"))


def test_file_ops_end_to_end_trace_does_not_mark_missing_pipeline(monkeypatch):
    from types import SimpleNamespace
    import verify_ownership as verifier
    class Client:
        def request_json(self,*args,**kw): return {"id":"x","state":"pending"}
        def request_bytes(self,*args,**kw): return b"",{},200
    runtime=SimpleNamespace(base_url="http://127.0.0.1:1234",e2e_completed={"a":dict.fromkeys(support.E2E_STAGES,False)})
    identity=SimpleNamespace(client=lambda *a:Client())
    client=verifier.TrackedActor(runtime,identity,"a")
    client.request_json("POST","/api/generations",expected_status=201)
    client.request_json("GET","/api/generations/x",expected_status=200)
    assert client.stages["generate"] and not client.stages["poll"] and not client.stages["pipeline"]


@pytest.mark.parametrize("line", ['{"release":true}\n','{"release":true}\r\n'])
def test_execution_release_accepts_windows_and_linux_line_endings(line):
    execution_helper().validate_release_line(line)


@pytest.mark.parametrize("line", ['', '{}\n', '{"release":1}\n', '{"release":false}\n',
                                 '{"release":true,"sql":"x"}\n', '{"release":true}', 'x'*129+'\n'])
def test_execution_release_refuses_eof_and_non_command(line):
    with pytest.raises(ValueError): execution_helper().validate_release_line(line)


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [False,True])
async def test_execution_holder_rolls_back_on_eof_or_self_timeout(timeout,monkeypatch,capsys):
    from io import StringIO
    from types import SimpleNamespace
    module = execution_helper()
    class Session:
        rolled_back = False
        async def execute(self,*a): pass
        async def scalar(self,*a): return module.content_id('create_create','asset')
        async def rollback(self): self.rolled_back = True
    session = Session()
    monkeypatch.setattr(module.sys,'stdin',StringIO(''))
    if timeout:
        ticks=iter([0,21])
        monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:next(ticks)))
        monkeypatch.setattr(module.threading,'Thread',lambda **kw:SimpleNamespace(start=lambda:None))
    with pytest.raises(ValueError): await module.hold_source(session,'create_create')
    assert session.rolled_back and json.loads(capsys.readouterr().out) == {'locked':True}


@pytest.mark.parametrize("failure", [False,True])
def test_waiter_window_clamps_commands_and_restores_cycle_deadline(failure,monkeypatch):
    runtime=support.OwnedRuntime(support.ROOT/'.env.example')
    original=runtime.deadline
    def fixture(operation,case):
        assert operation == 'lock_waiters' and runtime.deadline <= support.time.monotonic()+5
        if failure: raise support.HarnessError('command_failed')
        return {'lock_waiters':2}
    monkeypatch.setattr(runtime,'execution_fixture',fixture)
    if failure:
        with pytest.raises(support.HarnessError): runtime.observe_source_waiters('create_create')
    else: runtime.observe_source_waiters('create_create')
    assert runtime.deadline == original
@pytest.mark.parametrize("mode", ["unknown", "deadline", "cleanup", "both"])
def test_v2_failure_receipt_preserves_work_and_cleanup_failures(mode, monkeypatch, capsys):
    now = [0.0]
    monkeypatch.setattr(support.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(support, "command", lambda *a, **kw: "0" * 40)
    monkeypatch.setattr(support, "auth_proof", lambda *a: 12)
    class Runtime:
        project = "ownership-verify-012345abcdef"
        deadline = 360
        def __init__(self, *a): pass
        def preflight(self): now[0] += 1
        def start(self, *a): now[0] += 2
        def seed(self, *a): now[0] += 3
        def cleanup(self):
            now[0] += 4
            if mode in ("cleanup", "both"):
                raise RuntimeError("SECRET_CANARY")
    def scenario(runtime, identity):
        with support.phase(runtime, "worker"):
            if mode == "deadline":
                now[0] = 361
                raise support.HarnessError("cycle_deadline")
            if mode in ("unknown", "both"):
                raise RuntimeError("SECRET_CANARY")
        return 3
    row = support.verify_cycles(support.ROOT / ".env.example", 1,
        runtime_factory=Runtime, scenario=scenario)[0]
    assert row["passed"] is False
    assert row["cleanup_sec"] == 4
    assert row["work_sec"] == (361 if mode == "deadline" else 6)
    assert row["failure_code"] == ({"unknown":"unexpected_failure", "both":"unexpected_failure",
        "deadline":"deadline_exceeded", "cleanup":"none"}[mode])
    assert row["cleanup_failure_code"] == ("cleanup_failed" if mode in ("cleanup", "both") else "none")
    assert set(row["phase_seconds"]) <= support.PHASES
    assert "SECRET_CANARY" not in capsys.readouterr().out


def v2_receipts(suites=("ownership", "file-ops"), cycles=2):
    rows = []
    for suite in suites:
        for index in range(1, cycles + 1):
            row = dict(project="ownership-verify-" + format(len(rows)+1, "012x"),
                provider="mock", revision=support.REVISION, code_revision="0"*40,
                phase="validate", passed=True, cleanup=True, failure_code="none",
                cleanup_failure_code="none", suite=suite, cycle=index,
                work_sec=200, cleanup_sec=50, duration_sec=250)
            phases = {"preflight", "start", "seed", "auth", "validate", "cleanup"}
            if suite == "ownership":
                row.update(support.LEGACY_COUNTS, access_checks=348,
                           access_completed=dict.fromkeys(support.ACCESS_GROUPS, True))
                phases |= {"admission", "metadata", "smokes", "worker", "pipeline", "http_races", "expiry", "celery_completion"}
            else:
                row.update(support.FILE_COUNTS, file_ops_checks=100,
                    file_ops_completed=dict.fromkeys(support.FILE_OPS_GROUPS, True),
                    e2e_completed={actor:dict.fromkeys(support.E2E_STAGES, True) for actor in ("a", "b")})
                phases |= {"file_pre_auth", "file_post_auth", "e_a", "e_b"}
            row["phase_seconds"] = dict.fromkeys(phases, 1)
            rows.append(row)
    return rows


@pytest.mark.parametrize("changed,untracked,allowed", [("docs/current-work.md",".omo/local.md",True),
    ("scripts/verify_ownership.py","",False),("","backend/new.py",False)])
def test_v2_code_revision_refuses_dirty_or_untracked_code(changed, untracked, allowed, monkeypatch):
    import verify_ownership as verifier
    def command(args, **kwargs):
        if "rev-parse" in args: return "0"*40
        return changed if "diff" in args else untracked
    monkeypatch.setattr(verifier,"command",command)
    if allowed:
        assert verifier.code_revision() == "0"*40
    else:
        with pytest.raises(support.HarnessError, match="uncommitted_code"):
            verifier.code_revision()


@pytest.mark.parametrize("suite", ["ownership","file-ops"])
def test_v2_real_coordinator_receipt_shape_without_docker(suite, monkeypatch):
    # Unit seam proof only; these fake runtimes never count as real DB evidence.
    import verify_ownership as verifier
    monkeypatch.setattr(support, "command", lambda *a, **kw: "0"*40)
    monkeypatch.setattr(support, "auth_proof", lambda *a: 12)
    proof = v2_receipts((suite,), 1)[0]
    class Runtime:
        project = "ownership-verify-012345abcdef"
        def __init__(self, *a): pass
        def preflight(self): pass
        def start(self, *a): pass
        def seed(self, *a): pass
        def cleanup(self): pass
    monkeypatch.setattr(verifier, "file_ops_before_auth", lambda *a: None)
    monkeypatch.setattr(verifier, "file_ops_after_auth", lambda *a: None)
    def scenario(runtime, identity):
        for key, value in proof.items():
            if key not in support.BASE_RECEIPT:
                setattr(runtime, key, value)
        for name in proof["phase_seconds"]:
            if name not in {"preflight","start","seed","auth","validate","cleanup","file_pre_auth","file_post_auth"}:
                with support.phase(runtime, name): pass
        return proof["scenarios"]
    scenario.suite = suite
    scenario.requires_access = suite == "ownership"
    scenario.requires_file_ops = suite == "file-ops"
    rows = support.verify_cycles(support.ROOT / ".env.example", 1, runtime_factory=Runtime, scenario=scenario)
    assert support.validate_aggregate(rows, (suite,), 1, "0"*40)


@pytest.mark.parametrize("suite,cycles,complete", [("all",2,True),("all",1,False),
    ("ownership",2,False),("file-ops",2,False)])
def test_v2_coordinator_orders_fresh_suites_and_diagnostic_completion(suite, cycles, complete, monkeypatch):
    import verify_ownership as verifier
    monkeypatch.setattr(verifier, "code_revision", lambda: "0"*40)
    rows = v2_receipts(cycles=cycles)
    calls = []
    def verify(env_file, count, *, scenario, command_deadline):
        calls.append(scenario.suite)
        assert count == cycles and command_deadline > verifier.time.monotonic()
        return [row for row in rows if row["suite"] == scenario.suite]
    result = verifier.run_suites(support.ROOT / ".env.example", cycles, suite, verify=verify)
    assert calls == (["ownership","file-ops"] if suite == "all" else [suite])
    assert result["passed"] is True and result["complete"] is complete
    assert result["verified_cycles"] == len(calls)*cycles


@pytest.mark.parametrize("field,value", [("suite","custom"),("cycle",True),("cycle",2),
    ("code_revision","1"*40),("revision","0002"),("provider","vertex"),
    ("passed",False),("cleanup",False),("failure_code","none-secret"),
    ("auth_checks",True),("admission_checks",110),("access_checks",347),
    ("scenarios",0),("work_sec",361),("cleanup_sec",91),("duration_sec",451),
    ("work_sec",float("nan")),("phase","SECRET_CANARY")])
def test_v2_aggregate_refuses_wrong_or_partial_receipts(field, value):
    rows = v2_receipts()
    rows[0][field] = value
    with pytest.raises(support.HarnessError):
        support.validate_aggregate(rows, ("ownership","file-ops"), 2, "0"*40)


@pytest.mark.parametrize("change", ["missing","extra","duplicate","groups","stage",
    "unknown_stage","timing","timing_key","file_counter","file_legacy","reorder"])
def test_v2_aggregate_requires_exact_suites_groups_stages_projects_and_timing(change):
    rows = v2_receipts()
    if change == "missing": rows.pop()
    if change == "extra": rows[0]["SECRET_CANARY"] = True
    if change == "duplicate": rows[2]["project"] = rows[0]["project"]
    if change == "groups": rows[2]["file_ops_completed"]["V"] = False
    if change == "stage": del rows[2]["e2e_completed"]["b"]["pipeline"]
    if change == "unknown_stage": rows[2]["e2e_completed"]["a"]["SECRET_CANARY"] = True
    if change == "timing": rows[0]["phase_seconds"]["worker"] = float("inf")
    if change == "timing_key": del rows[0]["phase_seconds"]["worker"]
    if change == "file_counter": rows[2]["file_ops_checks"] = True
    if change == "file_legacy": rows[2]["admission_checks"] = 111
    if change == "reorder": rows.reverse()
    with pytest.raises(support.HarnessError):
        support.validate_aggregate(rows, ("ownership","file-ops"), 2, "0"*40)


@pytest.mark.parametrize("failure", ["cleanup", "drift", "deadline"])
def test_v2_coordinator_stops_on_failure_or_code_drift(failure, monkeypatch):
    import verify_ownership as verifier
    now = [1.0]
    monkeypatch.setattr(verifier.time, "monotonic", lambda: now[0])
    revisions = iter(("0"*40,"1"*40 if failure == "drift" else "0"*40))
    monkeypatch.setattr(verifier, "code_revision", lambda: next(revisions))
    rows, calls = v2_receipts(), []
    def verify(env_file, cycles, *, scenario, command_deadline):
        calls.append(scenario.suite)
        if failure == "cleanup": rows[0]["cleanup"] = False
        if failure == "deadline": now[0] = 1802
        return [row for row in rows if row["suite"] == scenario.suite]
    with pytest.raises(support.HarnessError):
        verifier.run_suites(support.ROOT / ".env.example", 2, "all", verify=verify)
    assert calls == (["ownership","file-ops"] if failure == "drift" else ["ownership"])


def test_v2_cli_default_and_secret_safe_failure(monkeypatch, capsys):
    import verify_ownership as verifier
    calls = []
    def run(env_file, cycles, suite):
        calls.append((cycles,suite))
        raise RuntimeError("SECRET_CANARY")
    monkeypatch.setattr(verifier, "run_suites", run)
    assert verifier.main([]) == 1
    assert calls == [(2,"ownership")]
    output = capsys.readouterr()
    assert "SECRET_CANARY" not in output.out + output.err
    assert json.loads(output.err)["complete"] is False


def test_v2_ownership_adapter_keeps_original_smokes_and_proofs(monkeypatch):
    import verify_ownership as verifier
    import smoke_mock_golden_path as golden
    import smoke_mock_retry_flow as retry
    import smoke_mock_i2v_duplicate_guard as duplicate
    from types import SimpleNamespace
    calls = []
    for name in ("admission_proof","access_proof","execution_proof"):
        monkeypatch.setattr(verifier, name, lambda *a, name=name: calls.append(name))
    for name, module in (("golden",golden),("retry",retry),("duplicate",duplicate)):
        monkeypatch.setattr(module, "run_smoke", lambda args, client, name=name: calls.append((name,client)))
    identity = SimpleNamespace(client=lambda base, actor: actor)
    runtime = SimpleNamespace(base_url="http://127.0.0.1:1234", deadline=verifier.time.monotonic()+360)
    assert verifier.scenarios(runtime, identity) == 3
    assert calls == ["admission_proof","access_proof",("golden","a"),("retry","a"),
                     ("duplicate","a"),"execution_proof"]


def test_v2_file_adapter_keeps_both_actors_complete_without_legacy_mutation(monkeypatch):
    import verify_ownership as verifier
    import smoke_mock_golden_path as golden
    import smoke_mock_retry_flow as retry
    import smoke_mock_i2v_duplicate_guard as duplicate
    from types import SimpleNamespace
    calls = []
    runtime = SimpleNamespace(deadline=verifier.time.monotonic()+360, file_ops_completed={})
    monkeypatch.setattr(verifier, "TrackedActor", lambda runtime, identity, case: case)
    for name, module in (("golden",golden),("retry",retry),("duplicate",duplicate)):
        monkeypatch.setattr(module, "run_smoke", lambda args, client, name=name: calls.append((name,client)))
    def pipeline(runtime, client):
        calls.append(("pipeline",client))
        runtime.e2e_completed[client] = dict.fromkeys(support.E2E_STAGES, True)
    monkeypatch.setattr(verifier, "pipeline_end_to_end", pipeline)
    def forbidden(*a): raise AssertionError("legacy proof in file suite")
    for name in ("admission_proof","access_proof","execution_proof"):
        monkeypatch.setattr(verifier, name, forbidden)
    assert verifier.file_ops_scenarios(runtime, object()) == 2
    assert calls == [("golden","a"),("retry","a"),("duplicate","a"),("pipeline","a"),
                     ("golden","b"),("retry","b"),("pipeline","b")]
    assert runtime.file_ops_completed["E"] is True
