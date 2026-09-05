import importlib.util
import json
from pathlib import Path

import pytest


def load():
    path = Path(__file__).resolve().parents[2] / "scripts/verify_master_admin.py"
    spec = importlib.util.spec_from_file_location("master_verifier_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_receipt_and_budget_contract():
    module = load()
    payload = dict(groups=dict.fromkeys(module.GROUPS, True), races=4, checks=60, complete=True)
    assert module.parse_proof(json.dumps(payload)) == payload
    module.activate()
    assert (module.base.WORK_SECONDS, module.base.CLEANUP_SECONDS) == (180, 60)
    from app.schema_revision import CODE_REVISION
    assert module.base.HEAD == CODE_REVISION


@pytest.mark.parametrize("change", [dict(complete=False), dict(groups={}), dict(races=3),
    dict(checks=59), dict(checks=True), dict(secret="forbidden")])
def test_invalid_receipt_rejected(change):
    module = load()
    value = dict(groups=dict.fromkeys(module.GROUPS, True), races=4, checks=60, complete=True)
    value.update(change)
    with pytest.raises(module.Failure):
        module.parse_proof(json.dumps(value))


@pytest.mark.parametrize("project", ["default", "creativeops", "master-admin-verify-../", "master-admin-verify-short"])
def test_project_guard(project):
    module = load()
    with pytest.raises(module.Failure):
        module.validate_project(project)
