#!/usr/bin/env python3
"""Own one disposable local PostgreSQL project for the G6 proof."""
import importlib.util
from pathlib import Path
import re
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
_BASE_SPEC = importlib.util.spec_from_file_location(
    "verify_credit_accounting_for_prompt", ROOT / "scripts/verify_credit_accounting.py"
)
base = importlib.util.module_from_spec(_BASE_SPEC)
_BASE_SPEC.loader.exec_module(base)
from runpy import run_path

HEAD = run_path(str(ROOT / "backend/app/schema_revision.py"))["CODE_REVISION"]
GROUPS = ("preflight", "admission", "terminal", "replay_race")
MINIMUM_CHECKS = 30


class Failure(RuntimeError):
    pass


def validate_project(project):
    if not re.fullmatch(r"prompt-credit-verify-[a-z0-9]{12}", project):
        raise Failure("target_refused")
    return project


def parse_proof(output):
    import json
    try:
        value = json.loads(output)
    except (TypeError, ValueError):
        raise Failure("receipt_invalid") from None
    if (not isinstance(value, dict)
            or set(value) != {"groups", "races", "checks", "provider_calls", "complete"}
            or value["complete"] is not True
            or not isinstance(value["groups"], dict)
            or set(value["groups"]) != set(GROUPS)
            or any(item is not True for item in value["groups"].values())
            or type(value["races"]) is not int or value["races"] < 1
            or type(value["checks"]) is not int or value["checks"] < MINIMUM_CHECKS
            or type(value["provider_calls"]) is not int or value["provider_calls"] < 1):
        raise Failure("receipt_invalid")
    return value


class Runtime(base.Runtime):
    def __init__(self, env_file, *, run=base.command):
        if Path(env_file).resolve() != (ROOT / ".env.example").resolve():
            raise Failure("env_file_refused")
        self.env = base.safe_env()
        self.run = run
        self.project = validate_project("prompt-credit-verify-" + uuid4().hex[:12])
        self.nonce = uuid4().hex
        self.context = None
        self.started = base.time.monotonic()
        self.deadline = self.started + base.WORK_SECONDS
        self.compose = None
        self.owned = False

    def configure(self, directory):
        super().configure(directory)
        import json
        config_path = Path(directory) / "compose.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["services"]["migrate"]["environment"].pop("ACCOUNTING_PROOF_PROJECT", None)
        config["services"]["migrate"]["environment"]["PROMPT_CREDIT_PROOF_PROJECT"] = self.project
        config_path.write_text(json.dumps(config), encoding="utf-8")


def _activate():
    base.HEAD = HEAD
    base.GROUPS = GROUPS
    base.PROOF = ROOT / "backend/tests/prompt_credit_support.py"
    base.EVIDENCE = ROOT / ".omo/evidence/issue-124"
    base.LABEL = "creativeops.prompt-credit-proof"
    base.Runtime = Runtime
    base.validate_project = validate_project
    base.parse_proof = parse_proof
    base.Failure = Failure


def main(argv=None):
    _activate()
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
