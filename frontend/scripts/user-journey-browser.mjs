// Reproducible UI acceptance against owned local services; never stub API responses.
import { chromium } from 'playwright';
import react from '@vitejs/plugin-react';
import { createServer } from 'vite';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
let vite, browser, phase = 'startup', external = 0;
const origin = 'http://127.0.0.1:18155';
const check = value => { if (!value) throw new Error('journey_check_failed'); };
try {
  let raw = '';
  for await (const chunk of process.stdin) { raw += chunk; check(raw.length < 4096); }
  const config = JSON.parse(raw);
  check(/^http:\/\/127\.0\.0\.1:[0-9]+$/.test(config.backend_url)
    && /^[A-Za-z0-9_-]{43}$/.test(config.secret));
  vite = await createServer({ root: process.cwd(), configFile: false, envFile: false,
    logLevel: 'silent', plugins: [react()], define: { 'import.meta.env.VITE_API_BASE': JSON.stringify('') },
    server: { host: '127.0.0.1', port: 18155, strictPort: true,
      proxy: { '/api': { target: config.backend_url }, '/files': { target: config.backend_url } } } });
  await vite.listen();
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ baseURL: origin, acceptDownloads: true,
    viewport: { width: 1440, height: 900 }, serviceWorkers: 'block' });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === origin) return route.continue();
    external++; return route.abort('blockedbyclient');
  });
  await context.addCookies([{ name: 'creativeops_session', value: config.secret,
    url: origin, httpOnly: true, sameSite: 'Lax', secure: false }]);
  const page = await context.newPage();
  page.setDefaultTimeout(20000);
  await page.goto('/generate');
  const health = await page.request.get('/api/health');
  check(health.ok() && (await health.json()).vertex.status === 'mock_provider');
  phase = 'enhance';
  await page.locator('.creative-prompt-field textarea').first().fill('A ceramic cup on a wooden desk');
  await page.getByRole('button', { name: '향상', exact: true }).click();
  await page.getByRole('heading', { name: '향상된 프롬프트 검토' }).waitFor();
  const draft = await page.getByRole('textbox', { name: '편집 가능한 향상 프롬프트 초안' }).inputValue();
  check(draft.length > 0);
  await page.getByRole('button', { name: '초안 수락', exact: true }).click();
  await page.getByText('프롬프트 향상을 수락했습니다.', { exact: false }).waitFor();
  phase = 'generate';
  const submitted = page.waitForResponse(r => r.url().endsWith('/api/generations') && r.request().method() === 'POST');
  await page.locator('button[type="submit"]').click();
  const response = await submitted;
  check(response.status() === 201 && response.request().postDataJSON().prompt === draft);
  const job = await response.json();
  await page.getByRole('heading', { name: /이미지 결과.*준비됨/ }).waitFor({ timeout: 60000 });
  await page.locator('img.asset-media').evaluate(image => image.decode());
  const output = resolve('../output/playwright/user-journey');
  await mkdir(output, { recursive: true });
  await page.locator('.creative-detail-grid').screenshot({ path: resolve(output, 'result.png'),
    mask: [page.locator('.prompt-detail')], animations: 'disabled' });
  phase = 'download';
  const finalResponse = await page.request.get(`/api/generations/${job.id}`);
  const final = await finalResponse.json();
  check(finalResponse.ok() && final.assets.length === 1);
  const downloaded = await page.request.get(final.assets[0].url);
  const bytes = await downloaded.body();
  check(downloaded.ok() && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])));
  phase = 'library';
  await page.goto('/history');
  const row = page.locator('.history-row').filter({ has: page.locator(`small[title="${job.id}"]`) });
  await row.waitFor();
  await row.click();
  await page.waitForURL(`**/jobs/${job.id}`);
  phase = 'usage';
  await page.goto('/usage');
  await page.getByRole('heading', { name: '플랜 및 사용량' }).waitFor();
  const usage = await page.request.get('/api/usage/me');
  const balance = await usage.json();
  check(usage.ok() && balance.credit.held_microcredits === 0 && balance.cycle.charged_microcredits > 0);
  check(external === 0);
  process.stdout.write(JSON.stringify({ passed: true, external_requests: external,
    prompt_review: true, accepted_prompt_matches: true, png_decoded: true,
    download_bytes: bytes.length, library_visible: true, credit_settled: true }));
} catch {
  process.stdout.write(JSON.stringify({ passed: false, phase }));
  process.exitCode = 1;
} finally {
  await browser?.close();
  await vite?.close();
}
