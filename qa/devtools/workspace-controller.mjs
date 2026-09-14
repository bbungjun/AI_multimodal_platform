import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createInterface } from 'node:readline';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { controlUid, pageId } from './image-controller.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const delay = ms => new Promise(done => setTimeout(done, ms));

async function main() {
  const [backend, output, profile, retryJob] = process.argv.slice(2);
  const child = spawn(process.execPath,
    [resolve(ROOT, 'qa/devtools/agent.mjs'), backend, output, profile, 'workspace', retryJob],
    { cwd: ROOT, stdio: ['pipe', 'pipe', 'ignore'] });
  const reader = createInterface({ input: child.stdout, crlfDelay: Infinity });
  const queue = [], waiters = [];
  reader.on('line', line => {
    let value; try { value = JSON.parse(line); } catch { value = { error: 'protocol' }; }
    const waiter = waiters.shift(); if (waiter) waiter(value); else queue.push(value);
  });
  const next = (timeout = 35_000) => queue.length ? Promise.resolve(queue.shift()) : Promise.race([
    new Promise(done => waiters.push(done)),
    new Promise((_, reject) => setTimeout(() => reject(Error('timeout')), timeout)),
  ]);
  const send = async command => {
    child.stdin.write(JSON.stringify(command) + '\n'); const response = await next();
    if (response.error || response.ok === false) throw Error('action'); return response;
  };
  const call = (name, args) => send({ op: 'call', name, arguments: args });
  const snapshot = page => call('take_snapshot', { pageId: page });
  const click = async (page, purpose, retries = 1) => {
    const seen = new Set();
    for (let attempt = 0; attempt < retries; attempt++) {
      const value = await snapshot(page);
      for (const control of value.controls ?? []) seen.add(control.purpose);
      const uid = controlUid(value, purpose);
      if (uid) { await call('click', { pageId: page, uid }); return; }
      await delay(750);
    }
    throw Error(`control_${purpose}_seen_${[...seen].sort().join('_') || 'none'}`);
  };
  const fill = async (page, purpose, fixture) => {
    const uid = controlUid(await snapshot(page), purpose); if (!uid) throw Error(`control_${purpose}`);
    await call('fill', { pageId: page, uid, fixture });
  };
  const checkpoint = async (page, phase, options = {}) => {
    for (let attempt = 0; attempt < (options.retries ?? 1); attempt++) {
      await delay(options.wait ?? 500); const response = await send({ op: 'checkpoint', phase });
      if (response.checkpoint?.passed) return;
    }
    throw Error(`checkpoint_${phase}`);
  };
  let stage = 'ready';
  try {
    const ready = await next(); if (ready.phase !== 'ready') throw Error('ready');
    const page = pageId(await call('list_pages', {}));
    await call('navigate_page', { pageId: page, type: 'url', url: 'http://127.0.0.1:18156/login' });
    stage = 'login';
    const pages = await call('list_pages', {});
    if (pages.pages?.includes('/login')) await call('wait_for', {
      pageId: page, text: ['Google로 계속하기'], timeout: 15000
    });
    let entry = await snapshot(page);
    const loginUid = controlUid(entry, 'login');
    if (loginUid) await call('click', { pageId: page, uid: loginUid });
    else throw Error('entry_unavailable');
    await checkpoint(page, 'login', { retries: 4, wait: 1000 });
    stage = 'history'; await click(page, 'history'); await checkpoint(page, 'history', { retries: 5, wait: 750 });
    await fill(page, 'state', 'failed'); await checkpoint(page, 'filtered', { retries: 5, wait: 750 });
    await click(page, 'next'); await checkpoint(page, 'page2', { retries: 5, wait: 750 });
    await click(page, 'previous'); await checkpoint(page, 'page1', { retries: 5, wait: 750 });
    stage = 'delete_cancel'; await click(page, 'delete'); await call('handle_dialog', { action: 'dismiss' });
    stage = 'detail'; await click(page, 'retry_row'); await checkpoint(page, 'detail', { retries: 4, wait: 750 });
    stage = 'retry'; await click(page, 'retry'); await checkpoint(page, 'retry_completed', { retries: 15, wait: 1000 });
    stage = 'usage'; await click(page, 'usage'); await checkpoint(page, 'usage', { retries: 5, wait: 750 });
    await call('navigate_page', { pageId: page, type: 'reload' });
    await checkpoint(page, 'usage_reloaded', { retries: 5, wait: 750 });
    await call('list_network_requests', { pageId: page, includePreservedRequests: true });
    await call('list_console_messages', { pageId: page, types: ['error', 'warn'], includePreservedMessages: true });
    await send({ op: 'verify' }); await send({ op: 'finish' });
    let closed = await next(); while (closed.phase !== 'browser_closed') closed = await next();
    if (closed.cleanup !== 0) throw Error('cleanup'); child.stdin.end();
    process.stdout.write(JSON.stringify({ complete: true, product_passed: closed.passed === true, cleanup: 0 }) + '\n');
  } catch (error) {
    child.stdin.end(); try { await Promise.race([once(child, 'exit'), delay(60_000)]); } catch {}
    process.stdout.write(JSON.stringify({ complete: false, error: `${stage}_${error.message}` }) + '\n');
    process.exitCode = 1;
  } finally { reader.close(); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
