"""Credential-free, isolated Postgres/Redis proof for G3. Never uses dev volumes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_FIELDS = {'project', 'provider', 'commit', 'revision', 'postgres', 'redis',
                  'redis_outage_recovery', 'metrics', 'cleanup'}
METRIC_FIELDS = {'concurrent_admissions', 'active_sessions_after_race', 'concurrent_touch_requests',
                 'effective_touch_writes', 'first_signup_race_requests', 'authentication_requests',
                 'authentication_p95_ms', 'flow_consume_requests', 'flow_consumed',
                 'flow_replay_refusals', 'expired_flow_refusals'}


def validate_project(project: str) -> str:
    if not re.fullmatch(r'auth-verify-[a-z0-9]{8,32}', project):
        raise ValueError('invalid isolated project')
    return project


class VerificationError(Exception):
    pass


def run(args, *, env=None, cwd=ROOT, timeout=180):
    try:
        result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        raise VerificationError('command_timeout_or_unavailable') from None
    if result.returncode:
        # No raw output: SQL/provider/request diagnostics can contain secrets.
        failed = re.findall(r'^FAILED (tests/[A-Za-z0-9_./]+::[A-Za-z0-9_]+)', result.stdout, re.M)
        locations = re.findall(r'(tests[/\\][A-Za-z0-9_./\\]+:\d+: [A-Za-z]+Error)', result.stdout)
        raise VerificationError('command_failed' + (': ' + ', '.join(failed + locations) if failed or locations else ''))
    return result.stdout.strip()


def resources(project):
    validate_project(project)
    containers = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project])
    volumes = run(['docker', 'volume', 'ls', '-q', '--filter', 'label=com.docker.compose.project=' + project])
    networks = run(['docker', 'network', 'ls', '-q', '--filter', 'label=com.docker.compose.project=' + project])
    return bool(containers or volumes or networks)


def port(value):
    if not re.fullmatch(r'127\.0\.0\.1:\d+', value):
        raise VerificationError('unexpected_bind_address')
    return int(value.rsplit(':', 1)[1])


def verify(env_file: Path):
    if env_file.resolve() != (ROOT / '.env.example').resolve():
        raise VerificationError('only_env_example_allowed')
    project = validate_project('auth-verify-' + uuid4().hex[:12])
    if resources(project):
        raise VerificationError('project_collision')
    env = os.environ.copy()
    env.update(AI_PROVIDER='mock', APP_ENV='test', AUTH_GOOGLE_CLIENT_ID='', AUTH_GOOGLE_CLIENT_SECRET='',
               AUTH_GOOGLE_REDIRECT_URI='', GOOGLE_APPLICATION_CREDENTIALS='', AUTH_COOKIE_SECURE='true')
    receipt = dict(project=project, provider='mock', commit=run(['git', 'rev-parse', 'HEAD']),
                   revision='0002_user_session_persistence', postgres='pending', redis='pending',
                   redis_outage_recovery='pending', metrics={}, cleanup='pending')
    with tempfile.TemporaryDirectory(prefix='auth-verifier-') as directory:
        folder = Path(directory)
        override = folder / 'compose.json'
        override.write_text(json.dumps({'services': {
            'db': {'environment': {'POSTGRES_USER': 'auth_verify', 'POSTGRES_PASSWORD': 'auth_verify_only',
                                   'POSTGRES_DB': 'auth_verify'}, 'ports': ['127.0.0.1::5432']},
            'redis': {'ports': ['127.0.0.1::6379']}}}), encoding='utf-8')
        compose = ['docker', 'compose', '--project-directory', str(ROOT), '--env-file', str(env_file),
                   '-p', project, '-f', str(ROOT / 'docker-compose.yml'), '-f', str(override)]
        failure = None
        try:
            run(compose + ['up', '-d', '--wait', 'db', 'redis'], env=env)
            db_port = port(run(compose + ['port', 'db', '5432'], env=env))
            redis_port = port(run(compose + ['port', 'redis', '6379'], env=env))
            env['DATABASE_URL'] = f'postgresql+asyncpg://auth_verify:auth_verify_only@127.0.0.1:{db_port}/auth_verify'
            env['AUTH_TEST_DATABASE_URL'] = env['DATABASE_URL']
            env['AUTH_TEST_REDIS_URL'] = f'redis://127.0.0.1:{redis_port}/1'
            env['AUTH_TEST_METRICS_PATH'] = str(folder / 'metrics.json')
            env['AUTH_TEST_FLOW_METRICS_PATH'] = str(folder / 'flow-metrics.json')
            run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], env=env, cwd=ROOT / 'backend')
            current = run([sys.executable, '-m', 'alembic', 'current'], env=env, cwd=ROOT / 'backend')
            if '0002_user_session_persistence (head)' not in current:
                raise VerificationError('unexpected_schema_revision')
            print('phase=postgres_and_redis', flush=True)
            run([sys.executable, '-m', 'pytest', 'tests/test_auth_service.py',
                 'tests/test_oauth_flow_store.py', 'tests/test_auth_api.py', '-q', '--tb=short'], env=env, cwd=ROOT / 'backend')
            receipt['postgres'] = receipt['redis'] = 'pass'
            receipt['metrics'] = json.loads((folder / 'metrics.json').read_text())
            receipt['metrics'].update(json.loads((folder / 'flow-metrics.json').read_text()))
            if (set(receipt['metrics']) != METRIC_FIELDS
                    or any(type(v) not in (int, float) or v < 0 for v in receipt['metrics'].values())):
                raise VerificationError('unsafe_metrics')
            run(compose + ['stop', 'redis'], env=env)
            print('phase=redis_outage', flush=True)
            env['AUTH_TEST_REDIS_DOWN'] = '1'
            run([sys.executable, '-m', 'pytest', 'tests/test_oauth_flow_store.py', '-k', 'real_redis',
                 '-q', '--tb=short'], env=env, cwd=ROOT / 'backend')
            run(compose + ['up', '-d', '--wait', 'redis'], env=env)
            # Docker may reassign a dynamic host port when a stopped container starts.
            redis_port = port(run(compose + ['port', 'redis', '6379'], env=env))
            env['AUTH_TEST_REDIS_URL'] = f'redis://127.0.0.1:{redis_port}/1'
            print('phase=redis_recovery', flush=True)
            env.pop('AUTH_TEST_REDIS_DOWN')
            run([sys.executable, '-m', 'pytest', 'tests/test_oauth_flow_store.py', '-k', 'real_redis',
                 '-q', '--tb=short'], env=env, cwd=ROOT / 'backend')
            receipt['redis_outage_recovery'] = 'pass'
        except VerificationError as error:
            failure = error
        finally:
            try:
                run(compose + ['down', '--volumes', '--remove-orphans'], env=env)
                if resources(project):
                    raise VerificationError('cleanup_incomplete')
                receipt['cleanup'] = 'pass'
            except VerificationError:
                failure = VerificationError(str(failure) + '; cleanup_failed' if failure else 'cleanup_failed')
        if failure:
            raise failure from None
    if set(receipt) != RECEIPT_FIELDS:
        raise VerificationError('unsafe_receipt')
    evidence = ROOT / '.omo/evidence/auth'
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (project + '.json')).write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env.example')
    args = parser.parse_args()
    try:
        verify(args.env_file)
    except VerificationError as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
