from pathlib import Path
from runpy import run_path
import json

import pytest


def load():
    module = run_path(str(Path(__file__).resolve().parents[2] / "scripts/verify_synthetic_seed.py"))
    module["activate"]()
    return module


def test_receipt_and_budget():
    module = load()
    value = dict(groups=dict.fromkeys(module["GROUPS"], True), races=1, checks=100, complete=True)
    assert module["parse_proof"](json.dumps(value)) == value
    assert (module["admin"].base.WORK_SECONDS, module["admin"].base.CLEANUP_SECONDS) == (600, 60)


@pytest.mark.parametrize("change", [dict(checks=99), dict(races=0), dict(groups={}), dict(complete=False)])
def test_partial_proof_rejected(change):
    module = load()
    value = dict(groups=dict.fromkeys(module["GROUPS"], True), races=1, checks=100, complete=True)
    value.update(change)
    with pytest.raises(module["Failure"]):
        module["parse_proof"](json.dumps(value))


@pytest.mark.parametrize("project", ["default", "creativeops", "master-seed-verify-../"])
def test_project_guard(project):
    module = load()
    with pytest.raises(module["Failure"]):
        module["validate_project"](project)
