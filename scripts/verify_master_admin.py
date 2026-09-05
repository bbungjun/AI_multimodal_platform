"""Own one disposable local PostgreSQL project for audited administration."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("master_proof_base", ROOT / "scripts/verify_credit_accounting.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
HEAD = base.HEAD
GROUPS = ("guards", "promotion", "plan", "bonus", "replay", "rollback", "append_only", "races")


class Failure(RuntimeError):
    pass


def validate_project(project):
    if not re.fullmatch(r"master-admin-verify-[a-z0-9]{12}", project):
        raise Failure("target_refused")
    return project


def parse_proof(output):
    try:
        value = json.loads(output)
    except (ValueError, TypeError):
        raise Failure("receipt_invalid") from None
    if (not isinstance(value, dict) or set(value) != {"groups", "races", "checks", "complete"}
            or value["complete"] is not True or not isinstance(value["groups"], dict)
            or set(value["groups"]) != set(GROUPS) or any(v is not True for v in value["groups"].values())
            or type(value["races"]) is not int or value["races"] < 4
            or type(value["checks"]) is not int or value["checks"] < 60):
        raise Failure("receipt_invalid")
    return value


def command(args, *, env, timeout, input=None):
    try:
        result = subprocess.run(args, cwd=ROOT, env=env, input=input, timeout=timeout,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        raise Failure("timeout") from None
    except OSError:
        raise Failure("command_failed") from None
    if result.returncode:
        if result.returncode == 124:
            raise Failure("timeout")
        match = re.fullmatch(r"master_proof_failed:([a-z_]+)\s*", result.stdout)
        phase = match[1] if match and match[1] in (*GROUPS, "guard", "done") else None
        raise Failure("proof_" + phase if phase else "command_failed")
    return result.stdout.rstrip("\r\n")


class Runtime(base.Runtime):
    def __init__(self, env_file, *, run=command):
        if Path(env_file).resolve() != (ROOT / ".env.example").resolve():
            raise Failure("env_file_refused")
        self.env = base.safe_env()
        self.run = run
        self.project = validate_project("master-admin-verify-" + uuid4().hex[:12])
        self.nonce = uuid4().hex
        self.context = None
        self.started = base.time.monotonic()
        self.deadline = self.started + 180
        self.compose = None
        self.owned = False

    def configure(self, directory):
        super().configure(directory)
        path = Path(directory) / "compose.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        environment = config["services"]["migrate"]["environment"]
        environment.pop("ACCOUNTING_PROOF_PROJECT", None)
        environment["MASTER_ADMIN_PROOF_PROJECT"] = self.project
        path.write_text(json.dumps(config), encoding="utf-8")


def activate():
    base.GROUPS = GROUPS
    base.PROOF = ROOT / "backend/tests/master_admin_support.py"
    base.EVIDENCE = ROOT / ".omo/evidence/issue-142"
    base.LABEL = "creativeops.master-admin-proof"
    base.WORK_SECONDS, base.CLEANUP_SECONDS = 180, 60
    base.Runtime, base.validate_project, base.parse_proof, base.Failure = Runtime, validate_project, parse_proof, Failure


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local mock audited administration proof")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.example")
    args = parser.parse_args(argv)
    activate()
    try:
        path = base.verify(args.env_file, run=command)
    except Failure as error:
        print("FAIL: " + str(error))
        return 1
    print("PASS: " + path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
