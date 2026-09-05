#!/usr/bin/env python3
"""Own one local, disposable PostgreSQL proof; never adopt a caller's database."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
from runpy import run_path

HEAD = run_path(str(ROOT / "backend/app/schema_revision.py"))["CODE_REVISION"]
GROUPS = ("init", "renewal", "plan", "bonus", "expiry", "idempotency", "transaction", "concurrency")
WORK_SECONDS, CLEANUP_SECONDS = 300, 90
PROOF = ROOT / "backend/tests/credit_lifecycle_support.py"
EVIDENCE = ROOT / ".omo/evidence/issue-116"
LABEL = "creativeops.credit-proof"


class Failure(RuntimeError):
    pass


def validate_project(project):
    if not re.fullmatch(r"credit-verify-[a-z0-9]{12}", project):
        raise Failure("target_refused")
    return project


def safe_env():
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE", "TEMP", "TMP", "DOCKER_CONFIG",
               "DOCKER_CONTEXT", "DOCKER_HOST", "COMSPEC", "PATHEXT", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
               "PROGRAMFILES", "PROGRAMFILES(X86)"}
    env = {key: value for key,value in os.environ.items() if key.upper() in allowed}
    if env.get("DOCKER_HOST"):
        raise Failure("docker_host_refused")
    env.update(AI_PROVIDER="mock", APP_ENV="test", GOOGLE_APPLICATION_CREDENTIALS="",
               AUTH_GOOGLE_CLIENT_ID="", AUTH_GOOGLE_CLIENT_SECRET="", AUTH_GOOGLE_REDIRECT_URI="")
    return env


def command(args, *, env, timeout, input=None):
    try:
        result = subprocess.run(args,cwd=ROOT,env=env,input=input,timeout=timeout,
                                capture_output=True,text=True,encoding="utf-8",errors="replace")
    except subprocess.TimeoutExpired:
        raise Failure("timeout") from None
    except OSError:
        raise Failure("command_failed") from None
    if result.returncode:
        if result.returncode == 124:
            raise Failure("timeout")
        match = re.fullmatch(r"lifecycle_proof_failed:(guard|init|renewal|plan|bonus|expiry|idempotency|transaction|concurrency|done)\s*",result.stdout)
        raise Failure("proof_"+match[1] if match else "command_failed")
    # Porcelain's leading status column is significant; only trim line endings.
    return result.stdout.rstrip("\r\n")


def parse_proof(output):
    try:
        value = json.loads(output)
    except (ValueError,TypeError):
        raise Failure("receipt_invalid") from None
    if (not isinstance(value,dict) or set(value) != {"groups","races","checks","complete"}
            or value["complete"] is not True or not isinstance(value["groups"],dict)
            or set(value["groups"]) != set(GROUPS) or any(v is not True for v in value["groups"].values())
            or type(value["races"]) is not int or value["races"] != 8
            or type(value["checks"]) is not int or value["checks"] < 80):
        raise Failure("receipt_invalid")
    return value


class Runtime:
    def __init__(self, env_file, *, run=command):
        if Path(env_file).resolve() != (ROOT/".env.example").resolve():
            raise Failure("env_file_refused")
        self.env = safe_env()
        self.run = run
        self.project = validate_project("credit-verify-"+uuid4().hex[:12])
        self.nonce = uuid4().hex
        self.context = None
        self.started = time.monotonic()
        self.deadline = self.started+WORK_SECONDS
        self.compose = None
        self.owned = False

    def call(self,args,*,input=None):
        remaining = self.deadline-time.monotonic()
        if remaining <= 0:
            raise Failure("timeout")
        result = self.run(args,env=self.env,timeout=min(180,remaining),input=input)
        if time.monotonic()>self.deadline:
            raise Failure("timeout")
        return result

    def docker(self,*args,input=None):
        return self.call(["docker"]+(["--context",self.context] if self.context else [])+list(args),input=input)

    def revision(self):
        sha = self.call(["git","rev-parse","HEAD"])
        if not re.fullmatch(r"[0-9a-f]{40}",sha):
            raise Failure("code_refused")
        status = self.call(["git","status","--porcelain","--untracked-files=normal"])
        if any(any(not path.startswith(("docs/",".omo/")) for path in line[3:].split(" -> "))
               for line in status.splitlines() if line.strip()):
            raise Failure("dirty_code_refused")
        return sha

    def resources(self):
        validate_project(self.project)
        result = []
        for kind,args in (("container",("ps","-aq")),("volume",("volume","ls","-q")),("network",("network","ls","-q"))):
            for name in self.docker(*args,"--filter","label=com.docker.compose.project="+self.project).splitlines():
                if name:
                    result.append((kind,name))
        return result

    def preflight(self):
        context = self.docker("context","show")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+",context):
            raise Failure("docker_context_refused")
        endpoint = self.docker("context","inspect",context,"--format","{{.Endpoints.docker.Host}}")
        if not (endpoint in ("npipe:////./pipe/dockerDesktopLinuxEngine","npipe:////./pipe/docker_engine")
                or re.fullmatch(r"unix:///[^\r\n]+",endpoint)):
            raise Failure("remote_docker_refused")
        self.context = context
        if self.docker("info","--format","{{.OSType}}") != "linux":
            raise Failure("docker_os_refused")
        if self.resources():
            raise Failure("project_collision")
        return self.revision()

    def configure(self,directory):
        config = json.loads(self.docker("compose","--env-file",str(ROOT/".env.example"),"-f",str(ROOT/"docker-compose.yml"),"config","--format","json"))
        dbname = self.project.replace("-","_")
        labels = {LABEL:self.nonce}
        db = config["services"]["db"]
        migrate = config["services"]["migrate"]
        db["environment"] = dict(POSTGRES_USER="credit",POSTGRES_PASSWORD="local_mock_only",POSTGRES_DB=dbname)
        db.pop("ports",None)
        db["volumes"] = [dict(type="volume",source="pgdata",target="/var/lib/postgresql/data")]
        db["healthcheck"]["test"] = ["CMD-SHELL","pg_isready -U credit -d "+dbname]
        migrate["environment"] = dict(DATABASE_URL=f"postgresql+asyncpg://credit:local_mock_only@db:5432/{dbname}",
            AI_PROVIDER="mock",APP_ENV="test",GOOGLE_APPLICATION_CREDENTIALS="",AUTH_GOOGLE_CLIENT_ID="",
            AUTH_GOOGLE_CLIENT_SECRET="",AUTH_GOOGLE_REDIRECT_URI="",CREDIT_PROOF_PROJECT=self.project)
        migrate.pop("volumes",None)
        for service in (db,migrate):
            service.pop("container_name",None)
            service["labels"] = labels
            service["networks"] = ["default"]
        selected = dict(services=dict(db=db,migrate=migrate),volumes=dict(pgdata=dict(labels=labels)),
                        networks=dict(default=dict(labels=labels)))
        path = Path(directory)/"compose.json"
        path.write_text(json.dumps(selected),encoding="utf-8")
        self.compose = ["compose","-p",self.project,"--env-file",str(ROOT/".env.example"),"-f",str(path)]

    def cleanup(self):
        validate_project(self.project)
        for kind,name in self.resources():
            field = ".Config.Labels" if kind == "container" else ".Labels"
            if self.docker(kind,"inspect",name,"--format",'{{ index '+field+' "'+LABEL+'" }}') != self.nonce:
                raise Failure("cleanup_ownership_refused")
        self.docker(*self.compose,"down","-v","--remove-orphans")
        if self.resources():
            raise Failure("cleanup_incomplete")


def receipt(runtime,sha,proof_result,work,cleanup_seconds,failure,cleanup_failure):
    if proof_result is not None:
        proof_result = parse_proof(json.dumps(proof_result))
    for path in (EVIDENCE,*EVIDENCE.parents):
        if path.is_symlink():
            raise Failure("evidence_refused")
        if path == ROOT:
            break
    if not re.fullmatch(r"[0-9a-f]{40}",sha):
        raise Failure("receipt_invalid")
    if not all(math.isfinite(v) and v>=0 for v in (work,cleanup_seconds)):
        raise Failure("receipt_invalid")
    complete = proof_result is not None and not failure and not cleanup_failure and work<=300 and cleanup_seconds<=90
    payload = dict(project=validate_project(runtime.project),commit=sha,revision=HEAD,provider="mock",complete=complete,
                   groups=proof_result["groups"] if proof_result else {},races=proof_result["races"] if proof_result else 0,
                   checks=proof_result["checks"] if proof_result else 0,work_seconds=round(work,3),
                   cleanup_seconds=round(cleanup_seconds,3),cleanup=not bool(cleanup_failure),
                   failure_code=failure or "none",cleanup_failure_code=cleanup_failure or "none")
    safe_codes = {"none","timeout","command_failed","receipt_invalid","code_changed","verification_failed",
                  "code_refused","dirty_code_refused"}
    safe_codes.update("proof_"+p for p in ("guard",*GROUPS,"done"))
    if payload["failure_code"] not in safe_codes or payload["cleanup_failure_code"] not in {"none","cleanup_failed"}:
        raise Failure("receipt_invalid")
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    output = EVIDENCE/(runtime.project+".json")
    output.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    return output


def verify(env_file,*,run=command):
    runtime = Runtime(env_file,run=run)
    sha = runtime.preflight()
    result = None
    failure = cleanup_failure = None
    with tempfile.TemporaryDirectory(prefix="credit-proof-") as directory:
        print("phase=configure",flush=True)
        runtime.configure(directory)
        try:
            runtime.owned = True
            print("phase=start project="+runtime.project,flush=True)
            runtime.docker(*runtime.compose,"build","migrate")
            runtime.docker(*runtime.compose,"up","-d","--wait","--wait-timeout","60","db")
            runtime.docker(*runtime.compose,"run","--rm","--no-deps","migrate")
            print("phase=lifecycle",flush=True)
            result = parse_proof(runtime.docker(*runtime.compose,"run","--rm","--no-deps","-T","migrate","python","-",input=PROOF.read_text(encoding="utf-8")))
            if runtime.revision() != sha:
                raise Failure("code_changed")
        except Failure as error:
            failure = str(error)
        except Exception:
            failure = "verification_failed"
        finally:
            work = time.monotonic()-runtime.started
            cleanup_start = time.monotonic()
            runtime.deadline = cleanup_start+CLEANUP_SECONDS
            print("phase=cleanup",flush=True)
            try:
                runtime.cleanup()
            except Exception:
                cleanup_failure = "cleanup_failed"
            cleanup_seconds = time.monotonic()-cleanup_start
    if work>WORK_SECONDS:
        failure = failure or "timeout"
    output = receipt(runtime,sha,result,work,cleanup_seconds,failure,cleanup_failure)
    if failure or cleanup_failure:
        raise Failure((failure or "none")+";"+(cleanup_failure or "none"))
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fixed local mock Credit lifecycle proof")
    parser.add_argument("--env-file",type=Path,default=ROOT/".env.example")
    args = parser.parse_args(argv)
    try:
        path = verify(args.env_file)
    except Failure as error:
        print("FAIL: "+str(error))
        return 1
    print("PASS: "+path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
