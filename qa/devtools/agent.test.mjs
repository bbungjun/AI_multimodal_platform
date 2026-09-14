import test from 'node:test';
import assert from 'node:assert/strict';
import { safeRoute, safeSnapshot, validateCommand, checksFor, networkRows, consoleSummary } from './agent.mjs';

test('evidence drops OAuth query, foreign origins and identity text', () => {
  assert.equal(safeRoute('http://127.0.0.1:18156/api/auth/google/callback?code=secret&state=secret'), '/api/auth/google/callback');
  assert.equal(safeRoute('https://foreign.test/api/auth/me'), 'other');
  assert.deepEqual(safeSnapshot('uid=1_1 button "Google로 계속하기"\nuid=1_2 textbox value="private"\nuid=1_3 button "person@example.test"'),
    ['uid=1_1 button "Google로 계속하기"']);
});

test('agent can only click the observed login control once', () => {
  const command = { op: 'call', name: 'click', arguments: { pageId: 1, uid: '1_1' } };
  assert.doesNotThrow(() => validateCommand(command, '1_1', false));
  assert.throws(() => validateCommand(command, null, false));
  assert.throws(() => validateCommand(command, '1_2', false));
  assert.throws(() => validateCommand(command, '1_1', true));
});

test('arbitrary scripts, foreign navigation and file outputs are refused', () => {
  for (const command of [
    { op: 'call', name: 'evaluate_script', arguments: { function: 'fetch("/")' } },
    { op: 'call', name: 'navigate_page', arguments: { pageId: 1, type: 'url', url: 'https://foreign.test' } },
    { op: 'call', name: 'take_snapshot', arguments: { pageId: 1, filePath: 'private.txt' } },
  ]) assert.throws(() => validateCommand(command, null, false));
});

test('login is not passed from UI alone or incomplete observation', () => {
  const base = { events: [], profile: true, workspace: true, clicked: true,
    external: 0, consoleErrors: 0, inspected: { network: true, console: true } };
  assert.equal(Object.values(checksFor(base)).every(Boolean), false);
  base.events = [['/api/auth/google/start', 307], ['/api/auth/google/callback', 303], ['/api/auth/me', 200]]
    .map(([route, status]) => ({ route, status }));
  assert.equal(Object.values(checksFor(base)).every(Boolean), true);
  assert.equal(Object.values(checksFor({ ...base, external: 1 })).every(Boolean), false);
  assert.equal(Object.values(checksFor({ ...base, consoleErrors: 1 })).every(Boolean), false);
  assert.equal(Object.values(checksFor({ ...base, workspace: false })).every(Boolean), false);
});

test('pinned DevTools network format is parsed without exposing OAuth values', () => {
  assert.deepEqual(networkRows('reqid=42 GET http://127.0.0.1:18156/api/auth/google/callback?code=private [303]'),
    [{ request_id: 42, route: '/api/auth/google/callback', status: 303 }]);
  assert.equal(networkRows('reqid=4 GET http://127.0.0.1:18156/api/auth/me [pending]')[0].status, 0);
  assert.deepEqual(networkRows('reqid=5 GET http://127.0.0.1:18156/favicon.ico [404]'),
    [{ request_id: 5, route: '/favicon.ico', status: 404 }]);
  assert.deepEqual(consoleSummary('Failed to load resource: the server responded with a status of 401 (Unauthorized)'),
    { route: 'other', kind: 'resource_load', http_status: 401 });
});
