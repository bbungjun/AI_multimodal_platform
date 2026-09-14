import test from 'node:test';
import assert from 'node:assert/strict';
import { controlUid, firstPageId, networkRows, parsePathProbe, parseProbe, safeRoute, scenarioResult,
  selectedPage, unexpectedConsoleCount } from './auth-contract.mjs';

test('routes and network evidence remove query values and foreign origins', () => {
  assert.equal(safeRoute('http://127.0.0.1:18156/api/auth/google/callback?code=private&state=private'),
    '/api/auth/google/callback');
  assert.equal(safeRoute('https://foreign.test/api/auth/me'), 'other');
  assert.deepEqual(networkRows([
    'reqid=1 GET http://127.0.0.1:18156/api/auth/google/start?ui=1 [307]',
    'reqid=2 GET http://127.0.0.1:18156/api/auth/google/callback?code=private [303]',
    'reqid=3 GET https://foreign.test/private [200]',
  ].join('\n')), [
    { route: '/api/auth/google/start', status: 307, method: 'GET' },
    { route: '/api/auth/google/callback', status: 303, method: 'GET' },
  ]);
});

test('snapshot parser returns only the requested control uid', () => {
  const snapshot = 'uid=1_1 button "계정 정보"\nuid=1_2 StaticText "identity@example.test"';
  assert.equal(controlUid(snapshot, '계정 정보'), '1_1');
  assert.equal(controlUid(snapshot, '로그아웃'), null);
});

test('selected page accepts only the owned origin', () => {
  assert.equal(firstPageId('0: about:blank [selected]'), 0);
  assert.deepEqual(selectedPage('0: http://127.0.0.1:18156/generate [selected]'),
    { pageId: 0, path: '/generate' });
  assert.throws(() => selectedPage('0: https://foreign.test/generate [selected]'));
});

test('probe parser accepts only one integer status', () => {
  assert.deepEqual(parseProbe('```json\n{"status":401}\n```'), { status: 401 });
  assert.throws(() => parseProbe('```json\n{"status":401,"body":"private"}\n```'));
});

test('path probe permits only contract routes', () => {
  assert.deepEqual(parsePathProbe('```json\n{"path":"/generate"}\n```'), { path: '/generate' });
  assert.throws(() => parsePathProbe('```json\n{"path":"/admin"}\n```'));
});

test('console summary permits expected auth 401 and router warning only', () => {
  assert.equal(unexpectedConsoleCount('msgid=1 Failed to load resource 401 Unauthorized'), 0);
  assert.equal(unexpectedConsoleCount('msgid=2 React Router Future Flag Warning'), 0);
  assert.equal(unexpectedConsoleCount('msgid=3 Uncaught TypeError'), 1);
});

const passingEvidence = () => ({ loginControlVisible: true, workspacePath: '/generate',
  logoutProbeStatus: 401, finalPath: '/login', network: [
    { route: '/api/auth/google/start', status: 307, method: 'GET' },
    { route: '/api/auth/google/callback', status: 303, method: 'GET' },
    { route: '/api/auth/me', status: 200, method: 'GET' },
  ] });

test('complete auth evidence maps to all seven contract assertions', () => {
  const result = scenarioResult(passingEvidence(), true);
  assert.equal(result.verdict, 'PASS');
  assert.equal(result.assertions.length, 7);
  assert.equal(result.assertions.every(row => row.passed), true);
  assert.deepEqual(result.blocked_reasons, []);
});

test('product mismatch is FAIL while incomplete tooling is BLOCKED', () => {
  const failed = passingEvidence();
  failed.finalPath = '/generate';
  assert.equal(scenarioResult(failed, true).verdict, 'FAIL');
  const blocked = scenarioResult(passingEvidence(), false);
  assert.equal(blocked.verdict, 'BLOCKED');
  assert.deepEqual(blocked.assertions, []);
  assert.deepEqual(blocked.blocked_reasons, ['devtools_execution_incomplete']);
});
