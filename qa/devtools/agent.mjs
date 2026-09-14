import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import puppeteer from 'puppeteer-core';
import { createRequire } from 'node:module';
import { createInterface } from 'node:readline';
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { once } from 'node:events';
import { ImageJourney, imageRoute } from './image-journey.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const ORIGIN = 'http://127.0.0.1:18156';
const AUTH_PATHS = new Set(['/api/auth/me', '/api/auth/google/start', '/api/auth/google/callback']);
const PUBLIC_DIAGNOSTIC_PATHS = new Set(['/favicon.ico', '/favicon.svg', '/vite.svg']);
const TOOLS = new Set(['list_pages', 'navigate_page', 'take_snapshot', 'click',
  'list_network_requests', 'list_console_messages']);
const emit = value => process.stdout.write(JSON.stringify(value) + '\n');

export function safeRoute(value) {
  try {
    const url = new URL(value);
    if (url.origin !== ORIGIN) return 'other';
    return AUTH_PATHS.has(url.pathname) || PUBLIC_DIAGNOSTIC_PATHS.has(url.pathname)
      ? url.pathname : imageRoute(url.pathname) ?? 'other';
  } catch { return 'other'; }
}

export function safeSnapshot(text) {
  // Only expose controls needed for this login proof. No profile names or input values.
  return text.split('\n').filter(line =>
    /uid=[\d_]+ button "(?:Google로 계속하기|계정 정보)"/.test(line))
    .map(line => line.match(/uid=[\d_]+ button "(?:Google로 계속하기|계정 정보)"/)[0]);
}

export function networkRows(text) {
  return text.split('\n').filter(row => /reqid=\d+/.test(row)).map(row => ({
    request_id: Number(row.match(/reqid=(\d+)/)?.[1]),
    route: safeRoute(row.match(/https?:\/\/[^\s]+/)?.[0]),
    status: Number(row.match(/\[(\d{3})\]/)?.[1] ?? 0),
  })).filter(row => row.route !== 'other');
}

export function consoleSummary(text, url = '') {
  return { route: safeRoute(url),
    kind: /Failed to load resource/.test(text) ? 'resource_load' :
      /React Router Future Flag Warning/.test(text) ? 'react_router_future' :
      /WebSocket/.test(text) ? 'websocket' : 'other',
    http_status: Number(text.match(/(?:status of |\[)(\d{3})/)?.[1] ?? 0) };
}

export function validateCommand(command, loginUid, clicked) {
  if (!command || typeof command !== 'object' || Array.isArray(command)) throw Error('command_refused');
  if (['tools', 'verify', 'finish'].includes(command.op) && Object.keys(command).length === 1) return;
  if (command.op !== 'call' || !TOOLS.has(command.name) ||
      Object.keys(command).sort().join(',') !== 'arguments,name,op') throw Error('command_refused');
  const args = command.arguments;
  if (!args || typeof args !== 'object' || Array.isArray(args)) throw Error('arguments_refused');
  const allowed = {
    list_pages: [], navigate_page: ['pageId', 'type', 'url'], take_snapshot: ['pageId'],
    click: ['pageId', 'uid'], list_network_requests: ['pageId', 'includePreservedRequests'],
    list_console_messages: ['pageId', 'types', 'includePreservedMessages'],
  }[command.name];
  if (Object.keys(args).some(key => !allowed.includes(key))) throw Error('arguments_refused');
  if (command.name !== 'list_pages' && (!Number.isInteger(args.pageId) || args.pageId < 0))
    throw Error('page_refused');
  if (command.name === 'navigate_page' && (args.url !== ORIGIN + '/login' || args.type !== 'url'))
    throw Error('origin_refused');
  if (command.name === 'click' && (!loginUid || args.uid !== loginUid || clicked)) throw Error('click_refused');
}

export function checksFor({ events, profile, workspace, clicked, external, consoleErrors, inspected }) {
  const seen = (path, status) => events.some(row => row.route === path && row.status === status);
  return {
    actual_login_click: clicked,
    login_start_307: seen('/api/auth/google/start', 307),
    callback_303: seen('/api/auth/google/callback', 303),
    authenticated_me_200: seen('/api/auth/me', 200) && profile,
    workspace_visible: workspace,
    no_external_page_requests: external === 0,
    no_unexpected_console_errors: consoleErrors === 0,
    devtools_network_inspected: inspected.network,
    devtools_console_inspected: inspected.console,
  };
}

async function main() {
  const [backend, output, profileDir, scenario = 'login'] = process.argv.slice(2);
  if (!['login', 'image'].includes(scenario)) throw Error('scenario_refused');
  const journey = scenario === 'image' ? new ImageJourney() : null;
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(backend ?? '') ||
      !output?.startsWith(resolve(ROOT, 'output/playwright') + '/') &&
      !output?.startsWith(resolve(ROOT, 'output/playwright') + '\\')) throw Error('start_refused');
  const frontendRequire = createRequire(resolve(ROOT, 'frontend/package.json'));
  const { createServer } = await import(pathToFileURL(resolve(dirname(frontendRequire.resolve('vite')), 'dist/node/index.js')).href);
  const react = (await import(pathToFileURL(frontendRequire.resolve('@vitejs/plugin-react')).href)).default;
  const events = [], actions = [], consoleRows = [], inspected = { network: false, console: false };
  let external = 0, consoleErrors = 0, profile = false, clicked = false, loginUid = null;
  let browser, vite, client, transport, chromeProcess, mcpPid, finished = false;
  const report = { scenario, passed: false, cleanup: 'pending', events, actions, console: consoleRows };
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const timeout = setTimeout(() => input.close(), 600_000);
  const pending = new Set();
  try {
    vite = await createServer({ root: resolve(ROOT, 'frontend'), configFile: false,
      envFile: false, logLevel: 'silent', plugins: [react()],
      server: { host: '127.0.0.1', port: 18156, strictPort: true,
        proxy: { '/api': { target: backend }, '/files': { target: backend } } },
      define: { 'import.meta.env.VITE_API_BASE': JSON.stringify('') } });
    await vite.listen();
    browser = await puppeteer.launch({ channel: 'chrome', headless: true, userDataDir: profileDir,
      debuggingPort: 0, defaultViewport: { width: 1440, height: 1000 },
      args: ['--disable-background-networking', '--disable-component-update'] });
    chromeProcess = browser.process();
    report.chrome_version = await browser.version();
    const [page] = await browser.pages();
    await page.setRequestInterception(true);
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.origin !== ORIGIN) { external++; void request.abort().catch(() => {}); }
      else void request.continue().catch(() => {});
    });
    page.on('response', response => {
      const route = safeRoute(response.url());
      if (route === 'other') return;
      events.push({ at: new Date().toISOString(), method: response.request().method(), route, status: response.status() });
      if (journey) {
        const task = journey.observe(response).catch(() => journey.failures.push('response_observation_failed'))
          .finally(() => pending.delete(task));
        pending.add(task);
      }
      if (route === '/api/auth/me' && response.status() === 200) {
        const task = response.json().then(value => { profile = value.role === 'user' && value.status === 'active'; })
          .catch(() => {}).finally(() => pending.delete(task));
        pending.add(task);
      }
    });
    // Browser emits a resource error for the expected initial anonymous /me 401.
    page.on('pageerror', () => { consoleErrors++; consoleRows.push({ kind: 'uncaught_exception' }); });
    page.on('console', message => {
      if (['error', 'warn'].includes(message.type())) consoleRows.push({
        type: message.type(), ...consoleSummary(message.text(), message.location().url) });
      if (message.type() === 'error' && !(safeRoute(message.location().url) === '/api/auth/me'
          && /401/.test(message.text()))) consoleErrors++;
    });
    const ws = new URL(browser.wsEndpoint());
    transport = new StdioClientTransport({ command: process.execPath,
      args: [resolve(ROOT, 'qa/devtools/node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js'),
        '--browserUrl', `http://127.0.0.1:${ws.port}`, '--no-usage-statistics', '--no-performance-crux',
        '--no-category-performance', '--redact-network-headers', '--no-source-maps'],
      env: { ...process.env, CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS: '1' }, stderr: 'pipe' });
    transport.stderr?.on('data', () => {});
    client = new Client({ name: 'creativeops-agent-login-qa', version: '1.0.0' });
    await client.connect(transport);
    mcpPid = transport.pid;
    const inventory = await client.listTools();
    report.mcp_version = JSON.parse(await readFile(resolve(ROOT, 'qa/devtools/node_modules/chrome-devtools-mcp/package.json'))).version;
    const call = async (name, args) => {
      const result = await client.callTool({ name, arguments: args }, undefined, { timeout: 30_000 });
      if (result.isError) throw Error('mcp_tool_failed');
      return (result.content ?? []).filter(item => item.type === 'text').map(item => item.text).join('\n');
    };
    emit({ phase: 'ready', scenario, origin: ORIGIN, commands: ['tools', 'call', 'verify', 'finish', ...(journey ? ['checkpoint'] : [])],
      ...(journey ? { fill_arguments: 'pageId, uid, fixture: original|reviewed (no literal prompt)',
        phases: ['login', 'original', 'draft', 'edited', 'accepted', 'completed', 'reloaded', 'history', 'revisited'] } : {}) });
    for await (const line of input) {
      const action = { id: `A${actions.length + 1}`, at: new Date().toISOString() };
      try {
        if (line.length > 4096 || actions.length >= (journey ? 80 : 40)) throw Error('command_limit');
        const command = JSON.parse(line);
        const prepared = journey?.prepare(command);
        if (!prepared) validateCommand(command, loginUid, clicked);
        action.op = command.op;
        if (command.op === 'checkpoint') {
          await Promise.all([...pending]);
          const pages = await call('list_pages', {});
          const pageId = Number(pages.match(/(?:^|\n)(\d+):/)?.[1]);
          if (!Number.isInteger(pageId)) throw Error('page_id_missing');
          action.checkpoint = await journey.checkpoint(prepared.phase, pageId, call);
          emit({ action: action.id, checkpoint: action.checkpoint });
        } else if (command.op === 'tools') {
          emit(inventory.tools.filter(tool => TOOLS.has(tool.name) || (journey && tool.name === 'fill'))
            .map(({ name, inputSchema }) => ({ name, inputSchema })));
        } else if (command.op === 'call') {
          action.tool = command.name;
          action.arguments = command.arguments;
          if (prepared?.purpose) action.purpose = prepared.purpose;
          const text = await call(command.name, prepared?.args ?? command.arguments);
          if (command.name === 'take_snapshot') {
            const controls = journey ? journey.snapshot(text) : safeSnapshot(text);
            if (!journey) loginUid = controls.find(row => row.includes('Google로 계속하기'))?.match(/uid=([\d_]+)/)?.[1] ?? null;
            action.controls = controls;
            emit({ action: action.id, controls });
          } else if (command.name === 'list_pages') {
            emit({ action: action.id, pages: text.replace(/https?:\/\/[^\s]+/g, value => {
              try { const u = new URL(value); return u.origin === ORIGIN ? ORIGIN + u.pathname.replace(/[0-9a-f-]{36}/gi, '{job}') : '[other-url]'; }
              catch { return '[url]'; }
            }) });
          } else if (command.name === 'list_network_requests') {
            // Return only allowlisted normalized routes, never headers or bodies.
            const rows = networkRows(text);
            inspected.network = [['/api/auth/google/start', 307], ['/api/auth/google/callback', 303],
              ['/api/auth/me', 200]].every(([route, status]) => rows.some(row => row.route === route && row.status === status));
            action.network = rows;
            emit({ action: action.id, devtools_requests: rows });
          } else if (command.name === 'list_console_messages') {
            inspected.console = true;
            action.console_entries = (text.match(/msgid=/g) ?? []).length;
            action.console = text.split('\n').filter(row => /msgid=/.test(row)).map(row => consoleSummary(row));
            emit({ action: action.id, console_entries: action.console_entries, unexpected_errors: consoleErrors,
              devtools_console: action.console, browser_console: consoleRows });
          } else {
            if (command.name === 'click' && (!journey || prepared?.purpose === 'login')) clicked = true;
            emit({ action: action.id, tool: command.name, ok: true });
          }
        } else {
          await Promise.all([...pending]);
          // Fixed read-only DOM probe through DevTools, no fetch or state mutation.
          const pageList = await call('list_pages', {});
          const pageId = Number(pageList.match(/(?:^|\n)(\d+):/)?.[1]);
          if (!Number.isInteger(pageId)) throw Error('page_id_missing');
          const probe = await call('evaluate_script', { pageId, function: '() => { const e = document.querySelector(".creative-generate"); const r = e?.getBoundingClientRect(); return { workspace: location.pathname === "/generate" && !!r && r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden" }; }' });
          const workspace = journey ? journey.loginWorkspace : /"workspace"\s*:\s*true/.test(probe);
          report.checks = checksFor({ events, profile, workspace, clicked, external, consoleErrors, inspected });
          if (journey) report.image = journey.result();
          emit({ action: action.id, checks: report.checks, ...(journey ? { image: report.image } : {}) });
          if (command.op === 'finish') { finished = true; action.ok = true; actions.push(action); break; }
        }
        action.ok = true;
      } catch { action.ok = false; emit({ action: action.id, error: 'action_failed_or_refused' }); }
      actions.push(action);
    }
    report.passed = finished && Object.values(report.checks ?? {}).length === 9 &&
      Object.values(report.checks).every(value => value === true) && (!journey || report.image?.passed === true);
    report.external_page_requests = external;
    report.unexpected_console_errors = consoleErrors;
  } catch (error) { report.error = 'driver_failed'; report.error_type = error.name; }
  finally {
    clearTimeout(timeout);
    input.close();
    const cleanupErrors = [];
    for (const [name, close] of [['mcp', () => client?.close()], ['chrome', () => browser?.close()], ['vite', () => vite?.close()]]) {
      try { await close(); } catch { cleanupErrors.push(name); }
    }
    if (chromeProcess && chromeProcess.exitCode === null && chromeProcess.signalCode === null) {
      try { await Promise.race([once(chromeProcess, 'exit'), new Promise((_, reject) => setTimeout(() => reject(Error()), 5000))]); }
      catch { cleanupErrors.push('chrome_process'); }
    }
    if (mcpPid) { try { process.kill(mcpPid, 0); cleanupErrors.push('mcp_process'); } catch {} }
    report.cleanup = cleanupErrors.length ? cleanupErrors : 0;
    await writeFile(resolve(output, 'browser.json'), JSON.stringify(report, null, 2) + '\n');
    emit({ phase: 'browser_closed', passed: report.passed, cleanup: report.cleanup });
    if (!report.passed || report.cleanup !== 0) process.exitCode = 1;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main().catch(error => { emit({ error: 'startup_failed', error_type: error.name,
    error_code: /^[A-Z_]+$/.test(error.code ?? '') ? error.code : null,
    locations: (error.stack ?? '').split('\n').slice(1).filter(row => row.includes('agent.mjs'))
      .map(row => row.match(/agent\.mjs:\d+:\d+/)?.[0]) }); process.exitCode = 1; });
}
