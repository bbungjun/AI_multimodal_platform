import importlib.util, json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
def load():
    spec=importlib.util.spec_from_file_location("verify_generation_credit",ROOT/"scripts/verify_generation_credit.py")
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def payload(module): return {"groups":dict.fromkeys(module.GROUPS,True),"races":2,"checks":120,"complete":True}
def test_fixed_receipt_contract():
    module=load(); value=payload(module); assert module.parse_proof(json.dumps(value))==value
@pytest.mark.parametrize("change",[{"complete":False},{"races":1},{"checks":119},{"groups":{}},{"private":"x"}])
def test_bad_receipt_refused(change):
    module=load(); value=payload(module); value.update(change)
    with pytest.raises(module.Failure,match="receipt_invalid"): module.parse_proof(json.dumps(value))
@pytest.mark.parametrize("value",["default","generation-credit-verify-123","generation-credit-verify-ABCDEF123456","generation-credit-verify-../"])
def test_project_guard(value):
    module=load()
    with pytest.raises(module.Failure,match="target_refused"): module.validate_project(value)
def test_private_env_refused_without_read(tmp_path):
    module=load()
    with pytest.raises(module.Failure,match="env_file_refused"): module.Runtime(tmp_path/".env")
