"""Owned full-size synthetic fixture proof, fixed600s work and60s cleanup."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("seed_admin_base", ROOT / "scripts/verify_master_admin.py")
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)
Failure = admin.Failure
GROUPS = ("guards", "dryrun", "seed", "distribution", "accounting", "replay", "denials", "readmodel")


def command(args, *, env, timeout, input=None):
    try:
        result = subprocess.run(args, cwd=ROOT, env=env, input=input, timeout=timeout,
            capture_output=True, text=True, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        raise Failure("timeout") from None
    except OSError:
        raise Failure("command_failed") from None
    if result.returncode:
        match = re.fullmatch(r"master_proof_failed:([a-z_]+):(SeedError|CreditAccountingError|CreditLifecycleError|IntegrityError|ProgrammingError|AssertionError|TypeError|AttributeError|other):(none|monthly_credit_exhausted|credit_plan_refused|credit_input_invalid|credit_account_inconsistent|user_concurrency_limit)\s*", result.stdout)
        if match and match[1] in GROUPS:
            print("seed_diagnostic="+match[2]+":"+match[3], flush=True)
            raise Failure("proof_"+match[1])
        raise Failure("timeout" if result.returncode == 124 else "command_failed")
    return result.stdout.rstrip("\r\n")


def validate_project(project):
    if not re.fullmatch(r"master-seed-verify-[a-f0-9]{12}", project):
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
            or type(value["races"]) is not int or value["races"] < 1
            or type(value["checks"]) is not int or value["checks"] < 100):
        raise Failure("receipt_invalid")
    return value


class Runtime(admin.Runtime):
    def __init__(self, env_file, *, run=command):
        super().__init__(env_file, run=run)
        self.project = validate_project("master-seed-verify-"+uuid4().hex[:12])
        self.deadline = self.started+600

    def call(self, args, *, input=None):
        remaining = self.deadline-admin.base.time.monotonic()
        if remaining <= 0:
            raise Failure("timeout")
        # Full-size fixture process uses this Goal's frozen600s total budget.
        # Other Docker/git commands retain the inherited180s command ceiling.
        limit = remaining if "exec" in args else min(180, remaining)
        result = self.run(args, env=self.env, timeout=limit, input=input)
        if admin.base.time.monotonic() > self.deadline:
            raise Failure("timeout")
        return result

    def configure(self, directory):
        super().configure(directory)
        path = Path(directory) / "compose.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        environment = config["services"]["migrate"]["environment"]
        environment.pop("MASTER_ADMIN_PROOF_PROJECT", None)
        environment["SYNTHETIC_SEED_PROOF_PROJECT"] = self.project
        path.write_text(json.dumps(config), encoding="utf-8")


def activate():
    admin.activate()
    admin.GROUPS = GROUPS
    base = admin.base
    base.GROUPS = GROUPS
    base.WORK_SECONDS = 600
    base.PROOF = ROOT / "backend/tests/synthetic_seed_support.py"
    base.EVIDENCE = ROOT / ".omo/evidence/issue-150"
    base.LABEL = "creativeops.synthetic-seed-proof"
    base.Runtime, base.validate_project, base.parse_proof = Runtime, validate_project, parse_proof


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local mock synthetic seed proof")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.example")
    args = parser.parse_args(argv)
    activate()
    try:
        path = admin.base.verify(args.env_file, run=command)
    except Failure as error:
        print("FAIL: "+str(error))
        return 1
    print("PASS: "+path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
