#!/usr/bin/env python3
"""Own one disposable local PostgreSQL project for emergency Session proof."""
import importlib.util
import json
import re
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'verify_accounting_for_emergency_sessions',
    ROOT / 'scripts/verify_credit_accounting.py',
)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
HEAD = '0006_credit_accounting_persistence'
GROUPS = (
    'login_gating', 'preview', 'operator_guards', 'revocation',
    'idempotency', 'admission', 'auth_race', 'rollback_cleanup',
)


class Failure(RuntimeError):
    pass


def validate_project(project):
    if not re.fullmatch(r'emergency-auth-verify-[a-z0-9]{12}', project):
        raise Failure('target_refused')
    return project


def parse_proof(output):
    try:
        value = json.loads(output)
    except (TypeError, ValueError):
        raise Failure('receipt_invalid') from None
    if (
        not isinstance(value, dict)
        or set(value) != {'groups', 'races', 'checks', 'complete'}
        or value['complete'] is not True
        or not isinstance(value['groups'], dict)
        or set(value['groups']) != set(GROUPS)
        or any(item is not True for item in value['groups'].values())
        or type(value['races']) is not int
        or value['races'] < 1
        or type(value['checks']) is not int
        or value['checks'] < 80
    ):
        raise Failure('receipt_invalid')
    return value


class Runtime(base.Runtime):
    def __init__(self, env_file, *, run=base.command):
        if Path(env_file).resolve() != (ROOT / '.env.example').resolve():
            raise Failure('env_file_refused')
        self.env = base.safe_env()
        self.run = run
        self.project = validate_project('emergency-auth-verify-' + uuid4().hex[:12])
        self.nonce = uuid4().hex
        self.context = None
        self.started = base.time.monotonic()
        self.deadline = self.started + 120
        self.compose = None
        self.owned = False

    def configure(self, directory):
        super().configure(directory)
        path = Path(directory) / 'compose.json'
        config = json.loads(path.read_text(encoding='utf-8'))
        environment = config['services']['migrate']['environment']
        environment.pop('ACCOUNTING_PROOF_PROJECT', None)
        environment['EMERGENCY_SESSION_PROOF_PROJECT'] = self.project
        environment['AUTH_LOGIN_ENABLED'] = 'false'
        path.write_text(json.dumps(config), encoding='utf-8')


def activate():
    base.HEAD = HEAD
    base.GROUPS = GROUPS
    base.MINIMUM_CHECKS = 80
    base.PROOF = ROOT / 'backend/tests/emergency_sessions_support.py'
    base.EVIDENCE = ROOT / '.omo/evidence/issue-99'
    base.LABEL = 'creativeops.emergency-session-proof'
    base.WORK_SECONDS = 120
    base.CLEANUP_SECONDS = 60
    base.Runtime = Runtime
    base.validate_project = validate_project
    base.parse_proof = parse_proof
    base.Failure = Failure


def main(argv=None):
    activate()
    return base.main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
