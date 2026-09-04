#!/usr/bin/env python3
"""Own one disposable local PostgreSQL project for the G7 proof."""
import importlib.util, json, re
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("verify_accounting_for_generation",ROOT/"scripts/verify_credit_accounting.py")
base=importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
HEAD="0006_credit_accounting_persistence"
GROUPS=("mapping_admission","imagen","veo","failure","retry","pipeline_success","pipeline_partial","replay_race")

class Failure(RuntimeError): pass
def validate_project(project):
    if not re.fullmatch(r"generation-credit-verify-[a-z0-9]{12}",project): raise Failure("target_refused")
    return project
def parse_proof(output):
    try: value=json.loads(output)
    except (TypeError,ValueError): raise Failure("receipt_invalid") from None
    if (not isinstance(value,dict) or set(value)!={"groups","races","checks","complete"} or value["complete"] is not True
            or set(value["groups"])!=set(GROUPS) or any(v is not True for v in value["groups"].values())
            or type(value["races"]) is not int or value["races"]<2 or type(value["checks"]) is not int or value["checks"]<120):
        raise Failure("receipt_invalid")
    return value
class Runtime(base.Runtime):
    def __init__(self,env_file,*,run=base.command):
        if Path(env_file).resolve() != (ROOT/".env.example").resolve():
            raise Failure("env_file_refused")
        self.env=base.safe_env(); self.run=run
        self.project=validate_project("generation-credit-verify-"+uuid4().hex[:12]); self.nonce=uuid4().hex
        self.context=None; self.started=base.time.monotonic(); self.deadline=self.started+360
        self.compose=None; self.owned=False
    def configure(self,directory):
        super().configure(directory)
        path=Path(directory)/"compose.json"; config=json.loads(path.read_text(encoding="utf-8"))
        config["services"]["migrate"]["environment"].pop("ACCOUNTING_PROOF_PROJECT",None)
        config["services"]["migrate"]["environment"]["GENERATION_CREDIT_PROOF_PROJECT"]=self.project
        path.write_text(json.dumps(config),encoding="utf-8")
def activate():
    base.HEAD=HEAD; base.GROUPS=GROUPS; base.MINIMUM_CHECKS=120
    base.PROOF=ROOT/"backend/tests/generation_credit_support.py"; base.EVIDENCE=ROOT/".omo/evidence/issue-127"
    base.LABEL="creativeops.generation-credit-proof"; base.Runtime=Runtime; base.validate_project=validate_project
    base.parse_proof=parse_proof; base.Failure=Failure; base.WORK_SECONDS=360
def main(argv=None): activate(); return base.main(argv)
if __name__=="__main__": raise SystemExit(main())
