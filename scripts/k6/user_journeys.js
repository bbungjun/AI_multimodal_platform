// Only verify_user_journey_load.py supplies ephemeral local fixture Sessions.
import http from 'k6/http';
import { sleep } from 'k6';
import exec from 'k6/execution';
import { Counter, Rate, Trend } from 'k6/metrics';
import crypto from 'k6/crypto';

const config = JSON.parse(__ENV.CREATIVEOPS_LOAD_CONFIG || '{}');
if (!/^http:\/\/127\.0\.0\.1:[0-9]+$/.test(config.base || '')
    || !Array.isArray(config.sessions) || config.sessions.length !== 64
    || config.sessions.some(s => !/^[A-Za-z0-9_-]{43}$/.test(s))) {
  throw new Error('owned_loopback_fixture_required');
}
const success = new Rate('journey_success');
const serverErrors = new Counter('server_errors');
const accepted = new Counter('accepted_journeys');
const completed = new Counter('completed_journeys');
const failures = new Counter('journey_failures');
const refusals = new Counter('policy_refusals');
const completion = new Trend('completion_ms', true);
const journeyDuration = new Trend('journey_ms', true);
const apiDuration = new Trend('api_ms', true);
const endpointNames = ['usage', 'enhance', 'create', 'poll', 'download', 'library'];
const thresholds = {
  journey_success: ['rate>=0.99'], server_errors: ['count==0'],
  api_ms: ['p(95)<1000', 'p(99)<2000'], completion_ms: ['p(95)<15000'],
  dropped_iterations: ['count==0'],
};
for (const endpoint of endpointNames) thresholds[`api_ms{endpoint:${endpoint}}`] = [];
for (const phase of ['usage', 'enhance', 'create', 'completion', 'delivery']) {
  thresholds[`journey_failures{phase:${phase}}`] = [];
}
for (const code of ['library_missing', 'held_not_released', 'active_request_remaining',
  'charge_not_increased', 'asset_count', 'asset_delivery', 'generation_failed', 'completion_timeout']) {
  thresholds[`journey_failures{code:${code}}`] = [];
}
for (const kind of ['image', 'video', 'pipeline']) thresholds[`journey_success{kind:${kind}}`] = [];
export const options = {
  scenarios: { journeys: { executor: 'constant-arrival-rate', rate: config.rate,
    timeUnit: config.time_unit, duration: config.duration,
    preAllocatedVUs: config.vus, maxVUs: config.vus, gracefulStop: '65s' } },
  thresholds, summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(95)', 'p(99)'],
  // Never retain URLs containing IDs, request errors, bodies, cookies or prompts.
  systemTags: ['status', 'method', 'name', 'scenario', 'expected_response'],
};
let params;
function request(method, path, body, endpoint, expected = 200) {
  const r = http.request(method, config.base + path, body ? JSON.stringify(body) : null,
    { ...params, tags: { name: endpoint, endpoint }, timeout: '10s', redirects: 0,
      responseType: endpoint === 'download' ? 'binary' : 'text' });
  apiDuration.add(r.timings.duration, { endpoint });
  serverErrors.add(r.status >= 500 ? 1 : 0);
  if (r.status === 429) refusals.add(1);
  if (r.status !== expected) throw new Error(`${endpoint}_http_${r.status}`);
  return r;
}
const parsed = r => { try { return r.json(); } catch { throw new Error('invalid_json'); } };
function finished(id) {
  const end = Date.now() + 60000;
  while (Date.now() < end) {
    const job = parsed(request('GET', `/api/generations/${id}`, null, 'poll'));
    if (job.state === 'completed') return job;
    if (job.state === 'failed') throw new Error('generation_failed');
    sleep(0.5);
  }
  throw new Error('completion_timeout');
}
function download(job) {
  if (job.assets.length !== 1) throw new Error('asset_count');
  const asset = job.assets[0];
  if (!/^\/files\/[A-Za-z0-9_.\/-]+$/.test(asset.url) || asset.url.includes('..')) throw new Error('asset_url');
  const r = request('GET', asset.url, null, 'download');
  const bytes = new Uint8Array(r.body);
  const signature = asset.kind === 'image'
    ? [137, 80, 78, 71, 13, 10, 26, 10].every((value, i) => bytes[i] === value)
    : [102, 116, 121, 112].every((value, i) => bytes[i + 4] === value);
  if (!signature || bytes.length !== asset.size_bytes
      || !String(r.headers['Content-Type']).includes(asset.mime)) throw new Error('asset_delivery');
}
export function setup() {
  const r = http.get(config.base + '/api/health', { tags: { name: 'health' }, redirects: 0 });
  if (r.status !== 200 || parsed(r).vertex.status !== 'mock_provider') throw new Error('mock_required');
}
export default function () {
  params = { headers: { 'Content-Type': 'application/json', Origin: 'http://127.0.0.1:18155',
    Cookie: `creativeops_session=${config.sessions[exec.vu.idInTest - 1]}` } };
  const started = Date.now();
  const choice = exec.scenario.iterationInTest % 10;
  const kind = choice < 6 ? 'image' : choice < 8 ? 'video' : 'pipeline';
  let phase = 'usage';
  try {
    const before = parsed(request('GET', '/api/usage/me', null, 'usage'));
    let prompt = 'A ceramic cup on a wooden desk';
    let enhancement;
    if (choice < 3) {
      phase = 'enhance';
      const bytes = new Uint8Array(crypto.randomBytes(16));
      const hex = Array.from(bytes, x => x.toString(16).padStart(2, '0')).join('');
      const requestId = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-a${hex.slice(17, 20)}-${hex.slice(20)}`;
      const draft = parsed(request('POST', '/api/prompts/enhance', { request_id: requestId,
        prompt, target_mode: 't2i', target_model: 'imagen-4.0-fast-generate-001',
        creativity_preset: 'faithful' }, 'enhance', 201));
      // Browser proof verifies review/accept; load uses that accepted payload contract.
      prompt = draft.enhanced; enhancement = draft.id;
    }
    phase = 'create';
    const submitAt = Date.now();
    let jobs;
    if (kind === 'pipeline') {
      const result = parsed(request('POST', '/api/pipelines', { image_prompt: prompt,
        video_prompt: 'Slow camera movement', image_model: 'imagen-4.0-fast-generate-001',
        video_model: 'veo-3.0-fast-generate-001', duration_sec: 4 }, 'create', 201));
      accepted.add(1, { kind }); phase = 'completion';
      jobs = [finished(result.parent.id), finished(result.child.id)];
    } else {
      const result = parsed(request('POST', '/api/generations', kind === 'image'
        ? { mode: 't2i', prompt, model: 'imagen-4.0-fast-generate-001', number_of_images: 1,
            ...(enhancement ? { enhancement_id: enhancement } : {}) }
        : { mode: 't2v', prompt, model: 'veo-3.0-fast-generate-001', duration_sec: 4 }, 'create', 201));
      accepted.add(1, { kind }); phase = 'completion'; jobs = [finished(result.id)];
    }
    completion.add(Date.now() - submitAt, { kind });
    phase = 'delivery';
    jobs.forEach(download);
    const library = parsed(request('GET', '/api/generations?limit=20', null, 'library'));
    if (!jobs.every(job => library.some(row => row.id === job.id))) throw new Error('library_missing');
    const after = parsed(request('GET', '/api/usage/me', null, 'usage'));
    if (after.credit.held_microcredits !== 0) throw new Error('held_not_released');
    if (after.concurrency.active_requests !== 0) throw new Error('active_request_remaining');
    if (after.cycle.charged_microcredits <= before.cycle.charged_microcredits) throw new Error('charge_not_increased');
    completed.add(1, { kind }); success.add(true, { kind });
  } catch (error) {
    success.add(false, { kind });
    const code = /^[a-z_]+(?:_http_[0-9]+)?$/.test(error.message) ? error.message : 'unexpected';
    failures.add(1, { phase, code });
  } finally { journeyDuration.add(Date.now() - started, { kind }); }
}
export function handleSummary(data) {
  // Only aggregate metrics; k6 never persists Session configuration or raw output.
  return { stdout: JSON.stringify({ metrics: data.metrics }) + '\n' };
}
