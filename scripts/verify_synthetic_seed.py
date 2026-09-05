"""Owned full-size synthetic fixture proof, fixed600s work and60s cleanup."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("seed_admin_base", ROOT / "scripts/verify_master_admin.py")
admin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admin)
Failure = admin.Failure
GROUPS = ("guards", "dryrun", "seed", "distribution", "accounting", "replay", "denials", "readmodel")


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
    def __init__(self, env_file, *, run=admin.command):
        super().__init__(env_file, run=run)
        self.project = validate_project("master-seed-verify-"+uuid4().hex[:12])
        self.deadline = self.started+600

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
        path = admin.base.verify(args.env_file, run=admin.command)
    except Failure as error:
        print("FAIL: "+str(error))
        return 1
    print("PASS: "+path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
