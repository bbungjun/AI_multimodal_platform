import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';
import { controlUid, pageId } from './image-controller.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const delay = ms => new Promise(done => setTimeout(done, ms));

async function main() {
  const [backend, output, profile] = process.argv.slice(2);
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(backend ?? '') || !output || !profile)
    throw Error('arguments_refused');
  const child = spawn(process.execPath,
    [resolve(ROOT, 'qa/devtools/agent.mjs'), backend, output, profile, 'video'],
    { cwd: ROOT, stdio: ['pipe', 'pipe', 'ignore'] });
  const reader = createInterface({ input: child.stdout, crlfDelay: Infinity });
  const queue = [], waiters = [];
  reader.on('line', line => {
    let value; try { value = JSON.parse(line); } catch { value = { error: 'protocol_invalid' }; }
    const waiter = waiters.shift(); if (waiter) waiter(value); else queue.push(value);
  });
  const next = (timeout = 35_000) => queue.length ? Promise.resolve(queue.shift()) : Promise.race([
    new Promise(done => waiters.push(done)),
    new Promise((_, reject) => setTimeout(() => reject(Error('protocol_timeout')), timeout)),
  ]);
  const send = async command => {
    child.stdin.write(JSON.stringify(command) + '\n');
    const result = await next();
    if (result.error || result.ok === false) throw Error('action_failed');
    return result;
  };
  const call = (name, args) => send({ op: 'call', name, arguments: args });
  const snapshot = page => call('take_snapshot', { pageId: page });
  const click = async (page, purpose) => {
    const uid = controlUid(await snapshot(page), purpose);
    if (!uid) throw Error('control_missing');
    return call('click', { pageId: page, uid });
  };
  const fill = async (page, purpose, fixture) => {
    const uid = controlUid(await snapshot(page), purpose);
    if (!uid) throw Error('control_missing');
    return call('fill', { pageId: page, uid, fixture });
  };
  const checkpoint = async (page, phase, options = {}) => {
    for (let attempt = 0; attempt < (options.retries ?? 1); attempt++) {
      await delay(options.wait ?? 500);
      const result = await send({ op: 'checkpoint', phase,
        ...(phase === 'empty' ? { accessibility_disabled: options.accessibilityDisabled } : {}) });
      if (result.checkpoint?.passed) return result;
    }
    throw Error('checkpoint_failed');
  };
  let stage = 'ready';
  try {
    const ready = await next();
    if (ready.phase !== 'ready' || ready.scenario !== 'video') throw Error('ready_invalid');
    const page = pageId(await call('list_pages', {}));
    await call('navigate_page', { pageId: page, type: 'url', url: 'http://127.0.0.1:18156/login' });
    await delay(750); stage = 'login'; await click(page, 'login');
    await checkpoint(page, 'login', { retries: 4, wait: 1000 });
    stage = 'mode'; await click(page, 't2v_mode'); await checkpoint(page, 'mode');
    stage = 'empty'; await fill(page, 'prompt', 'empty');
    const empty = await snapshot(page);
    const generate = empty.controls?.find(row => row.purpose === 'generate');
    await checkpoint(page, 'empty', { accessibilityDisabled: generate?.disabled === true });
    await fill(page, 'prompt', 'video');
    stage = 'allowed'; await click(page, 'generate');
    await checkpoint(page, 'allowed_completed', { retries: 15, wait: 1000 });
    stage = 'over_limit';
    await call('navigate_page', { pageId: page, type: 'url', url: 'http://127.0.0.1:18156/generate?mode=t2v' });
    await delay(750); await fill(page, 'duration', 'long'); await click(page, 'generate');
    await checkpoint(page, 'over_limit', { retries: 5, wait: 1000 });
    await call('list_network_requests', { pageId: page, includePreservedRequests: true });
    await call('list_console_messages', { pageId: page, types: ['error', 'warn'], includePreservedMessages: true });
    await send({ op: 'verify' }); await send({ op: 'finish' });
    let closed = await next(); while (closed.phase !== 'browser_closed') closed = await next();
    if (closed.cleanup !== 0) throw Error('cleanup_failed');
    child.stdin.end();
    process.stdout.write(JSON.stringify({ complete: true, product_passed: closed.passed === true, cleanup: 0 }) + '\n');
  } catch (error) {
    child.stdin.end();
    try { await Promise.race([once(child, 'exit'),
      new Promise((_, reject) => setTimeout(() => reject(Error('exit_timeout')), 20_000))]); }
    catch { child.kill(); }
    process.stdout.write(JSON.stringify({ complete: false, error: `${stage}_${error.message}` }) + '\n');
    process.exitCode = 1;
  } finally { reader.close(); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
