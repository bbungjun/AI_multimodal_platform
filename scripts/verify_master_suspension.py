"""Disposable suspension proof, reusing the guarded administration harness."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("suspension_admin_base", ROOT / "scripts/verify_master_admin.py")
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)
Failure = admin.Failure
GROUPS = ("guards", "sessions", "reactivation", "pending", "published", "pipeline", "rollback", "races")


def validate_project(project):
    if not re.fullmatch(r"master-suspension-verify-[a-z0-9]{12}", project):
        raise Failure("target_refused")
    return project


def parse_proof(output):
    value = admin.parse_proof(output)
    if value["checks"] < 80:
        raise Failure("receipt_invalid")
    return value


class Runtime(admin.Runtime):
    def __init__(self, env_file, *, run=admin.command):
        super().__init__(env_file, run=run)
        self.project = validate_project("master-suspension-verify-" + uuid4().hex[:12])

    def configure(self, directory):
        super().configure(directory)
        path = Path(directory) / "compose.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        environment = config["services"]["migrate"]["environment"]
        environment.pop("MASTER_ADMIN_PROOF_PROJECT", None)
        environment["MASTER_SUSPENSION_PROOF_PROJECT"] = self.project
        path.write_text(json.dumps(config), encoding="utf-8")


def activate():
    admin.activate()
    admin.GROUPS = GROUPS
    base = admin.base
    base.GROUPS = GROUPS
    base.PROOF = ROOT / "backend/tests/master_suspension_support.py"
    base.EVIDENCE = ROOT / ".omo/evidence/issue-144"
    base.LABEL = "creativeops.master-suspension-proof"
    base.Runtime, base.validate_project, base.parse_proof = Runtime, validate_project, parse_proof


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local mock suspension proof")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.example")
    args = parser.parse_args(argv)
    activate()
    try:
        path = admin.base.verify(args.env_file, run=admin.command)
    except Failure as error:
        print("FAIL: " + str(error))
        return 1
    print("PASS: " + path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
