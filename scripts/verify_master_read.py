"""Owned disposable read-model proof using the guarded administration harness."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("read_admin_base", ROOT / "scripts/verify_master_admin.py")
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)
Failure = admin.Failure
GROUPS = ("guards", "users", "cycles", "credits", "jobs", "audit", "privacy", "snapshot")


def validate_project(project):
    if not re.fullmatch(r"master-read-verify-[a-z0-9]{12}", project):
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
            or type(value["races"]) is not int or value["races"] < 3
            or type(value["checks"]) is not int or value["checks"] < 100):
        raise Failure("receipt_invalid")
    return value


class Runtime(admin.Runtime):
    def __init__(self, env_file, *, run=admin.command):
        super().__init__(env_file, run=run)
        self.project = validate_project("master-read-verify-"+uuid4().hex[:12])

    def configure(self, directory):
        super().configure(directory)
        path = Path(directory) / "compose.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        environment = config["services"]["migrate"]["environment"]
        environment.pop("MASTER_ADMIN_PROOF_PROJECT", None)
        environment["MASTER_READ_PROOF_PROJECT"] = self.project
        path.write_text(json.dumps(config), encoding="utf-8")


def activate():
    admin.activate()
    admin.GROUPS = GROUPS
    base = admin.base
    base.GROUPS = GROUPS
    base.PROOF = ROOT / "backend/tests/master_read_support.py"
    base.EVIDENCE = ROOT / ".omo/evidence/issue-146"
    base.LABEL = "creativeops.master-read-proof"
    base.Runtime, base.validate_project, base.parse_proof = Runtime, validate_project, parse_proof


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local mock Master read proof")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.example")
    args = parser.parse_args(argv)
    activate()
    try:
        path = admin.base.verify(args.env_file, run=admin.command)
    except Failure as error:
        print("FAIL: "+str(error))
        return 1
    print("PASS: "+path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
