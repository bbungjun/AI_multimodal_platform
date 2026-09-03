import importlib.util
import json
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location("verify_lifecycle",ROOT/"scripts/verify_credit_lifecycle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload(m):
    return dict(groups=dict.fromkeys(m.GROUPS,True),checks=80,races=8,complete=True)


@pytest.mark.parametrize("change",[dict(complete=False),dict(races=7),dict(races=True),dict(checks=79),dict(checks=True),
    dict(groups={}),dict(groups=dict.fromkeys(load().GROUPS,1)),dict(extra="private")])
def test_incomplete_or_extended_receipt_refused(change):
    m = load()
    value = payload(m)
    value.update(change)
    with pytest.raises(m.Failure,match="receipt_invalid"):
        m.parse_proof(json.dumps(value))


def test_complete_fixed_receipt():
    m = load()
    assert m.parse_proof(json.dumps(payload(m))) == payload(m)


@pytest.mark.parametrize("value",["default","creativeops-login-preview","credit-verify-123","credit-verify-123456ABCDEF","credit-verify-../"])
def test_project_guard(value):
    m = load()
    with pytest.raises(m.Failure,match="target_refused"):
        m.validate_project(value)


def test_private_dotenv_refused_without_read(tmp_path):
    m = load()
    with pytest.raises(m.Failure,match="env_file_refused"):
        m.Runtime(tmp_path/".env")
    with pytest.raises(m.Failure,match="env_file_refused"):
        m.Runtime(tmp_path/".env.example")


def test_ambient_provider_credentials_and_host_refused(monkeypatch):
    m = load()
    monkeypatch.setenv("DOCKER_HOST","tcp://remote:2375")
    with pytest.raises(m.Failure,match="docker_host_refused"):
        m.safe_env()
    monkeypatch.delenv("DOCKER_HOST")
    monkeypatch.setenv("DATABASE_URL","not-for-evidence")
    monkeypatch.setenv("ProgramFiles","system-plugin-path")
    monkeypatch.setenv("ProgramFiles(x86)","system-plugin-path-x86")
    monkeypatch.setenv("AUTH_GOOGLE_CLIENT_SECRET","not-for-evidence")
    env = m.safe_env()
    assert "DATABASE_URL" not in env and env["AUTH_GOOGLE_CLIENT_SECRET"] == ""
    assert env["AI_PROVIDER"] == "mock"
    folded = {key.upper():value for key,value in env.items()}
    assert folded["PROGRAMFILES"] == "system-plugin-path"
    assert folded["PROGRAMFILES(X86)"] == "system-plugin-path-x86"


def test_monotonic_deadline_clamps_and_does_not_retry(monkeypatch):
    m = load()
    monkeypatch.delenv("DOCKER_HOST",raising=False)
    clock = [0.0]
    monkeypatch.setattr(m.time,"monotonic",lambda:clock[0])
    calls = []
    r = m.Runtime(ROOT/".env.example",run=lambda args,**kwargs:calls.append(kwargs) or "")
    clock[0] = 295
    r.call(["fixture"])
    assert calls[0]["timeout"] == 5
    clock[0] = 301
    with pytest.raises(m.Failure,match="timeout"):
        r.call(["fixture"])
    assert len(calls) == 1


@pytest.mark.parametrize("status",[" M backend/app/credit_lifecycle.py","?? arbitrary.py","R  docs/x -> backend/x.py"])
def test_dirty_code_refused(status,monkeypatch):
    m = load()
    monkeypatch.delenv("DOCKER_HOST",raising=False)
    r = m.Runtime(ROOT/".env.example",run=lambda args,**kwargs: "f"*40 if args[1]=="rev-parse" else status)
    with pytest.raises(m.Failure,match="dirty_code_refused"):
        r.revision()


@pytest.mark.parametrize("endpoint,os_type",[("tcp://remote:2375","linux"),("unix:///safe","windows")])
def test_remote_or_nonlinux_daemon_refused(endpoint,os_type,monkeypatch):
    m = load()
    monkeypatch.delenv("DOCKER_HOST",raising=False)
    def run(args,**kwargs):
        if args[-1] == "show": return "desktop-linux"
        if "inspect" in args: return endpoint
        return os_type
    with pytest.raises(m.Failure,match="remote_docker_refused|docker_os_refused"):
        m.Runtime(ROOT/".env.example",run=run).preflight()


def test_command_timeout_and_raw_error_are_not_emitted(monkeypatch):
    m = load()
    def timeout(*args,**kwargs): raise subprocess.TimeoutExpired("sensitive",1,output="private")
    monkeypatch.setattr(m.subprocess,"run",timeout)
    with pytest.raises(m.Failure,match="^timeout$"):
        m.command([],env={},timeout=1)
    monkeypatch.setattr(m.subprocess,"run",lambda *a,**k:subprocess.CompletedProcess([],1,"private","credential"))
    with pytest.raises(m.Failure,match="^command_failed$"):
        m.command([],env={},timeout=1)


def test_real_command_preserves_porcelain_column_and_docs_only_are_allowed(monkeypatch):
    m = load()
    monkeypatch.delenv("DOCKER_HOST",raising=False)
    def run(args,**kwargs):
        output = "f"*40+"\n" if args[1] == "rev-parse" else " M docs/current-work.md\n?? .omo/\n"
        return subprocess.CompletedProcess(args,0,output,"")
    monkeypatch.setattr(m.subprocess,"run",run)
    assert m.Runtime(ROOT/".env.example").revision() == "f"*40


def test_only_db_and_migrate_fixed_config(tmp_path,monkeypatch):
    m = load()
    monkeypatch.delenv("DOCKER_HOST",raising=False)
    config = dict(services=dict(db=dict(image="postgres:16",ports=["5432"],healthcheck=dict(test=[])),
                               migrate=dict(build=dict(context="fixed")),backend=dict()))
    r = m.Runtime(ROOT/".env.example",run=lambda *a,**k:json.dumps(config))
    r.configure(tmp_path)
    selected = json.loads((tmp_path/"compose.json").read_text())
    assert set(selected["services"]) == {"db","migrate"}
    assert "ports" not in selected["services"]["db"]
    assert selected["services"]["migrate"]["environment"]["CREDIT_PROOF_PROJECT"] == r.project
    assert selected["volumes"]["pgdata"]["labels"][m.LABEL] == r.nonce


def test_cleanup_refuses_foreign_nonce_before_down(monkeypatch):
    m = load()
    monkeypatch.delenv("DOCKER_HOST",raising=False)
    calls = []
    r = m.Runtime(ROOT/".env.example",run=lambda a,**k:calls.append(a) or "foreign")
    r.resources = lambda:[("volume","fixture")]
    with pytest.raises(m.Failure,match="cleanup_ownership_refused"):
        r.cleanup()
    assert not any("down" in call for call in calls)


def test_receipt_does_not_convert_partial_groups_to_success(tmp_path,monkeypatch):
    m = load()
    monkeypatch.delenv("DOCKER_HOST",raising=False)
    monkeypatch.setattr(m,"EVIDENCE",tmp_path)
    r = m.Runtime(ROOT/".env.example")
    path = m.receipt(r,"f"*40,None,10,1,"proof_transaction",None)
    value = json.loads(path.read_text())
    assert not value["complete"] and value["groups"] == {} and value["cleanup"]
    assert "DATABASE_URL" not in path.read_text()


def test_cli_does_not_accept_target_source_or_cleanup_bypass():
    m = load()
    for flag in ("--project-name","--dsn","--source","--keep-volumes","--evidence-dir"):
        with pytest.raises(SystemExit):
            m.main([flag,"fixture"])
