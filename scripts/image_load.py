"""Owned, offline image-generation burst test; reports only aggregate evidence."""
import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

from mock_auth_support import OwnedRuntime, ROOT, HarnessError


class LoadRuntime(OwnedRuntime):
    def __init__(self, profile, output):
        super().__init__(ROOT / '.env.example')
        self.profile, self.output = profile, output
        self.deadline = time.monotonic() + 4000

    def override_text(self):
        source = super().override_text()
        # Baseline uses the actual committed production defaults, not the smoke
        # harness's increased 600/min allowance.
        source = source.replace('RATE_LIMIT_IMAGEN_PER_MIN: "600"', 'RATE_LIMIT_IMAGEN_PER_MIN: "5"')
        source = source.replace('RATE_LIMIT_GEMINI_PER_MIN: "600"', 'RATE_LIMIT_GEMINI_PER_MIN: "10"')
        source = source.replace('RATE_LIMIT_VEO_PER_MIN: "600"', 'RATE_LIMIT_VEO_PER_MIN: "1"')
        source = source.replace('  default:\n    labels:', '  default:\n    internal: true\n    labels:')
        return source

    def start(self, directory):
        # Internal Docker networks intentionally have no host port bindings.
        # Probe from inside the owned runtime instead of relaxing egress isolation.
        override = Path(directory) / 'compose.yml'
        override.write_text(self.override_text(), encoding='utf-8')
        self.compose = ['compose', '--project-directory', str(ROOT), '--env-file', str(ROOT / '.env.example'),
                        '--project-name', self.project, '-f', str(ROOT / 'docker-compose.yml'), '-f', str(override)]
        self.docker(*self.compose, 'config', '--quiet')
        self.started = True
        self.docker(*self.compose, 'up', '-d', '--build', 'db', 'redis', 'backend', 'dispatcher', 'worker')
        self.assert_owned()
        self.docker(*self.compose, 'exec', '-T', 'backend', 'python', '-c',
            "import json,time,urllib.request; "
            "exec(\"for _ in range(60):\\n try:\\n  h=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2)); assert h['ready'] and h['vertex']['status']=='mock_provider'; break\\n except Exception: time.sleep(1)\\nelse: raise RuntimeError('mock_readiness_timeout')\")")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=10000, choices=range(1, 10001), metavar='1..10000')
    parser.add_argument('--profile', choices=['baseline', 'capacity'], default='baseline')
    parser.add_argument('--drain-seconds', type=int, default=120)
    parser.add_argument('--request-timeout', type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.drain_seconds <= 3000 or not 1 <= args.request_timeout <= 600:
        parser.error('bounded deadlines required')
    output = ROOT / 'output' / 'image-load' / (args.profile + '-' + time.strftime('%Y%m%d-%H%M%S'))
    output.mkdir(parents=True, exist_ok=False)
    runtime = LoadRuntime(args.profile, output)
    receipt = dict(profile=args.profile, requested=args.count, complete=False,
                   revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                   tracked_diff=subprocess.check_output(['git', 'diff', '--stat'], cwd=ROOT, text=True).strip(),
                   provider='mock', network='internal', request_timeout_seconds=args.request_timeout,
                   drain_deadline_seconds=args.drain_seconds)
    started = time.monotonic()
    try:
        runtime.preflight()
        receipt['docker'] = json.loads(runtime.docker('info', '--format',
            '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}}}'))
        with tempfile.TemporaryDirectory(prefix='image-load-') as directory:
            try:
                print('Starting isolated mock runtime', flush=True)
                runtime.start(directory)
                runtime.assert_owned()
                print('Running authenticated burst: ' + str(args.count), flush=True)
                command = ['docker', '--context', runtime.context, *runtime.compose,
                           'run', '--rm', '--no-deps', '-T', 'backend', 'python',
                           'tests/image_load_support.py', '--count', str(args.count),
                           '--project', runtime.project, '--drain-seconds', str(args.drain_seconds),
                           '--request-timeout', str(args.request_timeout)]
                with (output / 'progress.jsonl').open('w', encoding='utf-8') as log:
                    result = subprocess.run(command, cwd=ROOT, env=runtime.env, stdout=log,
                                            stderr=subprocess.PIPE, text=True,
                                            timeout=args.drain_seconds + args.request_timeout + 180)
                # Only whitelisted diagnostic counters, never raw server logs.
                logs = runtime.docker(*runtime.compose, 'logs', '--no-color', 'backend', 'worker', 'dispatcher')
                receipt['diagnostics'] = {key: logs.count(needle) for key, needle in {
                    'pool_timeouts': 'QueuePool limit', 'connection_exhaustion': 'too many clients',
                    'lock_timeouts': 'LockNotAvailable', 'task_failures': 'raised unexpected',
                }.items()}
                records = [json.loads(line) for line in (output / 'progress.jsonl').read_text().splitlines()]
                summaries = [item['result'] for item in records if 'result' in item]
                if summaries:
                    receipt.update(summaries[-1])
                receipt['process_exit'] = result.returncode
                if result.returncode and not summaries:
                    # Exception class only, never stderr which can contain SQL.
                    receipt['failure'] = 'load_process_failed'
            finally:
                runtime.cleanup()
                receipt['cleanup_remaining'] = len(runtime.resources(cleanup=True))
    except Exception as error:
        receipt['failure'] = str(error) if isinstance(error, HarnessError) else type(error).__name__
    receipt['elapsed_seconds'] = round(time.monotonic() - started, 3)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'receipt': str(output / 'receipt.json'), 'complete': receipt['complete'],
                      'failure': receipt.get('failure'), 'cleanup_remaining': receipt.get('cleanup_remaining')}))
    return 0 if receipt.get('passed') and receipt.get('cleanup_remaining') == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
