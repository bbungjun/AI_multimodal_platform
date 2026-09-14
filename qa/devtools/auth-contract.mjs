import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import puppeteer from 'puppeteer-core';
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { once } from 'node:events';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const ORIGIN = 'http://127.0.0.1:18156';
const ROUTES = new Set(['/api/auth/me', '/api/auth/google/start', '/api/auth/google/callback',
  '/api/auth/logout', '/favicon.ico', '/favicon.svg', '/vite.svg']);
const ASSERTIONS = [
  ['auth.login_control_visible', ['ui_snapshot']],
  ['auth.start_redirect', ['network']],
  ['auth.callback_redirect', ['network']],
  ['auth.session_resolves', ['network']],
  ['auth.workspace_route', ['url']],
  ['auth.logout_invalidates', ['network']],
  ['auth.login_route_restored', ['url']],
];

export function safeRoute(value) {
  try {
    const url = new URL(value);
    return url.origin === ORIGIN && ROUTES.has(url.pathname) ? url.pathname : 'other';
  } catch { return 'other'; }
}

export function networkRows(text) {
  return text.split('\n').filter(row => /reqid=\d+/.test(row)).map(row => ({
    route: safeRoute(row.match(/https?:\/\/[^\s]+/)?.[0]),
    status: Number(row.match(/\[(\d{3})\]/)?.[1] ?? 0),
    method: row.match(/reqid=\d+\s+([A-Z]+)/)?.[1] ?? 'UNKNOWN',
  })).filter(row => row.route !== 'other');
}

export function selectedPage(text) {
  for (const line of text.split('\n')) {
    const match = line.match(/(?:^|\s)(\d+):\s+(https?:\/\/[^\s]+)/);
    if (!match) continue;
    const url = new URL(match[2]);
    if (url.origin === ORIGIN) return { pageId: Number(match[1]), path: url.pathname };
  }
  throw Error('page_missing');
}

export function firstPageId(text) {
  const value = Number(text.match(/(?:^|\n)(\d+):/)?.[1]);
  if (!Number.isInteger(value) || value < 0) throw Error('page_missing');
  return value;
}

export function controlUid(text, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return text.match(new RegExp(`uid=([\\d_]+) button "${escaped}"`))?.[1] ?? null;
}

export function parseProbe(text) {
  const match = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (!match) throw Error('probe_invalid');
  const value = JSON.parse(match[1]);
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).sort().join(',') !== 'status' || !Number.isInteger(value.status))
    throw Error('probe_invalid');
  return value;
}

export function parsePathProbe(text) {
  const match = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (!match) throw Error('probe_invalid');
  const value = JSON.parse(match[1]);
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).sort().join(',') !== 'path' || !['/generate', '/login'].includes(value.path))
    throw Error('probe_invalid');
  return value;
}

export function unexpectedConsoleCount(text) {
  return text.split('\n').filter(row => /msgid=/.test(row)).filter(row =>
    !/React Router Future Flag Warning/.test(row) &&
    !(/Failed to load resource/.test(row) && /(?:401|Unauthorized)/.test(row))).length;
}

export function scenarioResult(evidence, technicalComplete) {
  const passed = {
    'auth.login_control_visible': evidence.loginControlVisible === true,
    'auth.start_redirect': evidence.network.some(row => row.route === '/api/auth/google/start' && row.status === 307),
    'auth.callback_redirect': evidence.network.some(row => row.route === '/api/auth/google/callback' && row.status === 303),
    'auth.session_resolves': evidence.network.some(row => row.route === '/api/auth/me' && row.status === 200),
    'auth.workspace_route': evidence.workspacePath === '/generate',
    'auth.logout_invalidates': evidence.logoutProbeStatus === 401,
    'auth.login_route_restored': evidence.finalPath === '/login',
  };
  const assertions = technicalComplete
    ? ASSERTIONS.map(([id, sources]) => ({ id, passed: passed[id], evidence: sources })) : [];
  const verdict = !technicalComplete ? 'BLOCKED' : assertions.some(row => !row.passed) ? 'FAIL' : 'PASS';
  return { scenario_id: 'auth_login', selected: true, verdict, assertions,
    blocked_reasons: technicalComplete ? [] : ['devtools_execution_incomplete'] };
}

async function main() {
  const [backend, output, profileDir] = process.argv.slice(2);
  const outputRoot = resolve(ROOT, 'output/playwright');
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(backend ?? '') ||
      !(output?.startsWith(outputRoot + '/') || output?.startsWith(outputRoot + '\\')))
    throw Error('start_refused');
  const frontendRequire = createRequire(resolve(ROOT, 'frontend/package.json'));
  const { createServer } = await import(pathToFileURL(
    resolve(dirname(frontendRequire.resolve('vite')), 'dist/node/index.js')).href);
  const react = (await import(pathToFileURL(frontendRequire.resolve('@vitejs/plugin-react')).href)).default;
  const evidence = { loginControlVisible: false, workspacePath: null, logoutProbeStatus: 0,
    finalPath: null, network: [] };
  const report = { schema_version: 1, scenario_id: 'auth_login', provider: 'mock',
    passed: false, technical_complete: false, external_page_requests: 0,
    unexpected_console_errors: 0, evidence: null, scenario_result: null,
    cleanup: { browser: 1, mcp: 1, vite: 1 } };
  let browser, vite, client, transport, chromeProcess, mcpPid;
  let technicalComplete = false;
  let phase = 'vite_start';
  const runtimeRows = [];
  try {
    vite = await createServer({ root: resolve(ROOT, 'frontend'), configFile: false,
      envFile: false, logLevel: 'silent', plugins: [react()],
      server: { host: '127.0.0.1', port: 18156, strictPort: true,
        proxy: { '/api': { target: backend }, '/files': { target: backend } } },
      define: { 'import.meta.env.VITE_API_BASE': JSON.stringify('') } });
    await vite.listen();
    phase = 'chrome_start';
    browser = await puppeteer.launch({ channel: 'chrome', headless: true, userDataDir: profileDir,
      debuggingPort: 0, defaultViewport: { width: 1440, height: 1000 },
      args: ['--disable-background-networking', '--disable-component-update'] });
    chromeProcess = browser.process();
    report.chrome_version = await browser.version();
    const [page] = await browser.pages();
    await page.setRequestInterception(true);
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.origin !== ORIGIN) {
        report.external_page_requests++;
        void request.abort().catch(() => {});
      } else void request.continue().catch(() => {});
    });
    page.on('response', response => {
      const route = safeRoute(response.url());
      if (route !== 'other') runtimeRows.push({ route, status: response.status(),
        method: response.request().method() });
    });

    const ws = new URL(browser.wsEndpoint());
    phase = 'mcp_connect';
    transport = new StdioClientTransport({ command: process.execPath,
      args: [resolve(ROOT, 'qa/devtools/node_modules/chrome-devtools-mcp/build/src/bin/chrome-devtools-mcp.js'),
        '--browserUrl', `http://127.0.0.1:${ws.port}`, '--no-usage-statistics', '--no-performance-crux',
        '--no-category-performance', '--redact-network-headers', '--no-source-maps'],
      env: { ...process.env, CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS: '1' }, stderr: 'pipe' });
    transport.stderr?.on('data', () => {});
    client = new Client({ name: 'creativeops-agent-qa-executor', version: '1.0.0' });
    await client.connect(transport);
    mcpPid = transport.pid;
    report.mcp_version = JSON.parse(await readFile(
      resolve(ROOT, 'qa/devtools/node_modules/chrome-devtools-mcp/package.json'))).version;
    const call = async (name, args) => {
      const result = await client.callTool({ name, arguments: args }, undefined, { timeout: 30_000 });
      if (result.isError) throw Error('mcp_tool_failed');
      return (result.content ?? []).filter(item => item.type === 'text').map(item => item.text).join('\n');
    };
    phase = 'login_navigation';
    let current = { pageId: firstPageId(await call('list_pages', {})), path: null };
    await call('navigate_page', { pageId: current.pageId, type: 'url', url: ORIGIN + '/login' });
    await call('wait_for', { pageId: current.pageId, text: ['Google로 계속하기'], timeout: 10_000 });
    phase = 'login_snapshot';
    let snapshot = await call('take_snapshot', { pageId: current.pageId });
    const loginUid = controlUid(snapshot, 'Google로 계속하기');
    evidence.loginControlVisible = loginUid !== null;
    if (!loginUid) throw Error('login_control_missing');
    phase = 'login_click';
    await call('click', { pageId: current.pageId, uid: loginUid });
    phase = 'authenticated_wait';
    await call('wait_for', { pageId: current.pageId, text: ['계정 정보'], timeout: 15_000 });
    phase = 'authenticated_page';
    evidence.workspacePath = parsePathProbe(await call('evaluate_script', { pageId: current.pageId,
      function: '() => ({ path: location.pathname })' })).path;
    phase = 'login_network';
    evidence.network.push(...networkRows(await call('list_network_requests', {
      pageId: current.pageId, includePreservedRequests: true })));

    phase = 'account_snapshot';
    snapshot = await call('take_snapshot', { pageId: current.pageId });
    const accountUid = controlUid(snapshot, '계정 정보');
    if (!accountUid) throw Error('account_control_missing');
    phase = 'account_click';
    await call('click', { pageId: current.pageId, uid: accountUid });
    phase = 'logout_control_wait';
    await call('wait_for', { pageId: current.pageId, text: ['로그아웃'], timeout: 10_000 });
    phase = 'logout_snapshot';
    snapshot = await call('take_snapshot', { pageId: current.pageId });
    const logoutUid = controlUid(snapshot, '로그아웃');
    if (!logoutUid) throw Error('logout_control_missing');
    phase = 'logout_click';
    await call('click', { pageId: current.pageId, uid: logoutUid });
    phase = 'logged_out_wait';
    await call('wait_for', { pageId: current.pageId, text: ['Google로 계속하기'], timeout: 10_000 });
    phase = 'logged_out_page';
    evidence.finalPath = parsePathProbe(await call('evaluate_script', { pageId: current.pageId,
      function: '() => ({ path: location.pathname })' })).path;
    phase = 'logout_probe';
    const probe = parseProbe(await call('evaluate_script', { pageId: current.pageId,
      function: 'async () => ({ status: (await fetch("/api/auth/me", { credentials: "include" })).status })' }));
    evidence.logoutProbeStatus = probe.status;
    phase = 'logout_network';
    evidence.network.push(...networkRows(await call('list_network_requests', {
      pageId: current.pageId, includePreservedRequests: true })));
    phase = 'console_inspection';
    const consoleText = await call('list_console_messages', {
      pageId: current.pageId, types: ['error', 'warn'], includePreservedMessages: true });
    report.unexpected_console_errors = unexpectedConsoleCount(consoleText);
    technicalComplete = true;
  } catch (error) {
    report.error = 'devtools_execution_failed';
    report.error_type = error?.name ?? 'Error';
    report.failure_phase = phase;
  } finally {
    const cleanup = { browser: 0, mcp: 0, vite: 0 };
    for (const [name, close] of [['mcp', () => client?.close()], ['browser', () => browser?.close()],
      ['vite', () => vite?.close()]]) {
      try { await close(); } catch { cleanup[name] = 1; }
    }
    if (chromeProcess && chromeProcess.exitCode === null && chromeProcess.signalCode === null) {
      try { await Promise.race([once(chromeProcess, 'exit'),
        new Promise((_, reject) => setTimeout(() => reject(Error()), 5000))]); }
      catch { cleanup.browser = 1; }
    }
    if (mcpPid) { try { process.kill(mcpPid, 0); cleanup.mcp = 1; } catch {} }
    report.cleanup = cleanup;
    const unique = new Map();
    for (const row of evidence.network) unique.set(`${row.method}:${row.route}:${row.status}`, row);
    evidence.network = [...unique.values()].sort((a, b) =>
      `${a.route}:${a.status}:${a.method}`.localeCompare(`${b.route}:${b.status}:${b.method}`));
    const runtimeKeys = new Set(runtimeRows.map(row => `${row.method}:${row.route}:${row.status}`));
    const devtoolsKeys = new Set(evidence.network.map(row => `${row.method}:${row.route}:${row.status}`));
    report.network_cross_check = [...devtoolsKeys].every(key => runtimeKeys.has(key));
    report.evidence = { login_control_visible: evidence.loginControlVisible,
      workspace_path: evidence.workspacePath, logout_probe_status: evidence.logoutProbeStatus,
      final_path: evidence.finalPath, network: evidence.network };
    report.scenario_result = scenarioResult(evidence, technicalComplete);
    report.technical_complete = technicalComplete;
    report.passed = technicalComplete && report.scenario_result.verdict === 'PASS' &&
      report.external_page_requests === 0 && report.unexpected_console_errors === 0 &&
      report.network_cross_check && Object.values(cleanup).every(value => value === 0);
    await writeFile(resolve(output, 'browser.json'), JSON.stringify(report, null, 2) + '\n');
    if (!report.passed) process.exitCode = 1;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main().catch(error => {
    process.stdout.write(JSON.stringify({ complete: false, error: 'startup_failed',
      error_type: error?.name ?? 'Error' }) + '\n');
    process.exitCode = 1;
  });
}
