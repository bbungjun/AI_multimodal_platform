import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const delay = ms => new Promise(resolveDelay => setTimeout(resolveDelay, ms));

export function controlUid(message, purpose) {
  return message?.controls?.find(row => row.purpose === purpose && row.disabled === false)?.uid ?? null;
}

export function pageId(message) {
  const value = Number(message?.pages?.match(/(?:^|\n)(\d+):/)?.[1]);
  if (!Number.isInteger(value) || value < 0) throw Error('page_missing');
  return value;
}

async function main() {
  const [backend, output, profile] = process.argv.slice(2);
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(backend ?? '') || !output || !profile)
    throw Error('arguments_refused');
  const child = spawn(process.execPath,
    [resolve(ROOT, 'qa/devtools/agent.mjs'), backend, output, profile, 'image'],
    { cwd: ROOT, stdio: ['pipe', 'pipe', 'ignore'] });
  const input = createInterface({ input: child.stdout, crlfDelay: Infinity });
  const queue = [];
  const waiters = [];
  let stage = 'ready';
  input.on('line', line => {
    let value;
    try { value = JSON.parse(line); } catch { value = { error: 'protocol_invalid' }; }
    const waiter = waiters.shift();
    if (waiter) waiter(value); else queue.push(value);
  });
  const next = async (timeout = 35_000) => {
    if (queue.length) return queue.shift();
    return await Promise.race([
      new Promise(resolveNext => waiters.push(resolveNext)),
      new Promise((_, reject) => setTimeout(() => reject(Error('protocol_timeout')), timeout)),
    ]);
  };
  const send = async command => {
    child.stdin.write(JSON.stringify(command) + '\n');
    const response = await next();
    if (response.error || response.ok === false) throw Error('action_failed');
    return response;
  };
  const call = (name, args) => send({ op: 'call', name, arguments: args });
  const snapshot = page => call('take_snapshot', { pageId: page });
  const clickPurpose = async (page, purpose) => {
    const snap = await snapshot(page);
    const uid = controlUid(snap, purpose);
    if (!uid) throw Error('control_missing');
    await call('click', { pageId: page, uid });
  };
  const fillPurpose = async (page, purpose, fixture) => {
    const snap = await snapshot(page);
    const uid = controlUid(snap, purpose);
    if (!uid) throw Error('control_missing');
    await call('fill', { pageId: page, uid, fixture });
  };
  const checkpoint = async (page, phase, { retries = 1, wait = 500 } = {}) => {
    for (let attempt = 0; attempt < retries; attempt++) {
      await delay(wait);
      const response = await send({ op: 'checkpoint', phase });
      if (response.checkpoint?.passed === true) return response.checkpoint;
    }
    throw Error('checkpoint_failed');
  };
  try {
    const ready = await next();
    if (ready.phase !== 'ready' || ready.scenario !== 'image') throw Error('ready_invalid');
    stage = 'login';
    const page = pageId(await call('list_pages', {}));
    await call('navigate_page', { pageId: page, type: 'url', url: 'http://127.0.0.1:18156/login' });
    await delay(750);
    await clickPurpose(page, 'login');
    await checkpoint(page, 'login', { retries: 3, wait: 1000 });
    stage = 'empty';
    await checkpoint(page, 'empty');
    stage = 'original';
    await fillPurpose(page, 'original', 'original');
    await checkpoint(page, 'original');
    stage = 'discard';
    await clickPurpose(page, 'enhance');
    await checkpoint(page, 'draft_discard', { retries: 5, wait: 1000 });
    await clickPurpose(page, 'discard');
    await checkpoint(page, 'discarded');
    stage = 'keep';
    await clickPurpose(page, 'enhance');
    await checkpoint(page, 'draft_keep', { retries: 5, wait: 1000 });
    await clickPurpose(page, 'keep');
    await checkpoint(page, 'kept');
    stage = 'accept';
    await clickPurpose(page, 'enhance');
    await checkpoint(page, 'draft', { retries: 5, wait: 1000 });
    await fillPurpose(page, 'draft', 'reviewed');
    await checkpoint(page, 'edited');
    await clickPurpose(page, 'accept');
    await checkpoint(page, 'accepted');
    stage = 'generation';
    await clickPurpose(page, 'generate');
    await checkpoint(page, 'completed', { retries: 12, wait: 1000 });
    stage = 'reload';
    await call('navigate_page', { pageId: page, type: 'reload' });
    await checkpoint(page, 'reloaded', { retries: 5, wait: 1000 });
    stage = 'history';
    await clickPurpose(page, 'history');
    await checkpoint(page, 'history', { retries: 5, wait: 1000 });
    stage = 'revisit';
    await clickPurpose(page, 'job');
    await checkpoint(page, 'revisited', { retries: 5, wait: 1000 });
    await call('list_network_requests', { pageId: page, includePreservedRequests: true });
    await call('list_console_messages', { pageId: page, types: ['error', 'warn'], includePreservedMessages: true });
    await send({ op: 'verify' });
    await send({ op: 'finish' });
    const closed = await next();
    if (closed.phase !== 'browser_closed' || closed.cleanup !== 0)
      throw Error('browser_result_failed');
    child.stdin.end();
    process.stdout.write(JSON.stringify({ complete: true, scenario: 'image',
      product_passed: closed.passed === true, cleanup: 0 }) + '\n');
  } catch (error) {
    child.stdin.end();
    try {
      let closed = await next(15_000);
      while (closed.phase !== 'browser_closed') closed = await next(15_000);
    } catch { child.kill(); }
    process.stdout.write(JSON.stringify({ complete: false, error: `${stage}_${error.message}` }) + '\n');
    process.exitCode = 1;
  } finally {
    input.close();
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}
