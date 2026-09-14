import { createHash } from 'node:crypto';

export const ORIGINAL = 'A small blue ceramic cup on a wooden studio desk.';
const EDIT_SUFFIX = ' Keep one cup, with soft light from the left.';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PHASES = ['login', 'empty', 'original', 'draft_discard', 'discarded', 'draft_keep', 'kept',
  'draft', 'edited', 'accepted', 'completed', 'reloaded', 'history', 'revisited'];
const LABELS = new Map([
  ['Google로 계속하기', 'login'], ['계정 정보', 'account'], ['프롬프트', 'original'],
  ['편집 가능한 향상 프롬프트 초안', 'draft'], ['향상', 'enhance'], ['초안 수락', 'accept'],
  ['버리기', 'discard'], ['원본 유지', 'keep'],
  ['생성', 'generate'], ['기록', 'history'],
]);

export function imageRoute(path) {
  if (['/api/prompts/enhance', '/api/generations'].includes(path)) return path;
  if (/^\/api\/generations\/[0-9a-f-]{36}$/.test(path)) return '/api/generations/{job}';
  if (/^\/files\/[0-9a-f-]{36}\/output\.png$/.test(path)) return '/files/{job}/output.png';
  return null;
}

export function parseProbe(text) {
  const match = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (!match) throw Error('probe_response_invalid');
  const value = JSON.parse(match[1]);
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('probe_response_invalid');
  return value;
}

export class ImageJourney {
  constructor() {
    this.controls = new Map();
    this.attempts = new Set();
    this.clickCounts = {};
    this.postCounts = { enhancement: 0, generation: 0 };
    this.enhancement = null;
    this.jobId = null;
    this.assetPath = null;
    this.assetId = null;
    this.jobCompleted = false;
    this.jobReads = 0;
    this.historyContainsJob = false;
    this.file = null;
    this.fileReads = 0;
    this.baseline = null;
    this.payloadMatches = false;
    this.enhancementMatches = false;
    this.failures = [];
    this.checkpoints = {};
    this.steps = [];
    this.reloadReads = null;
    this.revisitReads = null;
    this.lastPhase = null;
    this.emptyAccessibilityDisabled = null;
  }

  get edited() { return this.enhancement ? this.enhancement.enhanced + EDIT_SUFFIX : null; }
  get loginWorkspace() { return this.checkpoints.login?.workspace === true; }

  snapshot(text) {
    this.controls.clear();
    for (const line of text.split('\n')) {
      const match = line.match(/uid=([\d_]+) (button|textbox|link) "([^"]*)"/);
      if (!match) continue;
      const [, uid, role, name] = match;
      let purpose = LABELS.get(name);
      if (role === 'link' && /^기록(?:\s+\d+)?$/.test(name)) purpose = 'history';
      if (role === 'button' && this.jobId && name.includes(this.jobId.slice(0, 8)) && name.includes('작업')) purpose = 'job';
      if (!purpose) continue;
      const expectedRole = ['original', 'draft'].includes(purpose) ? 'textbox' : purpose === 'history' ? 'link' : 'button';
      if (role !== expectedRole) continue;
      this.controls.set(uid, { uid, role, purpose, disabled: /(?:^|\s)disabled(?:\s|$)/.test(line) });
    }
    return [...this.controls.values()];
  }

  prepare(command) {
    if (command.op === 'checkpoint') {
      const fields = command.phase === 'empty' ? 'accessibility_disabled,op,phase' : 'op,phase';
      if (Object.keys(command).sort().join(',') !== fields || !PHASES.includes(command.phase)
          || (command.phase === 'empty' && typeof command.accessibility_disabled !== 'boolean'))
        throw Error('phase_refused');
      if (command.phase !== PHASES[Object.keys(this.checkpoints).length]) throw Error('phase_order');
      if (command.phase === 'empty') this.emptyAccessibilityDisabled = command.accessibility_disabled;
      return { phase: command.phase };
    }
    if (command.op !== 'call' || !['click', 'fill', 'navigate_page'].includes(command.name)) return null;
    if (Object.keys(command).sort().join(',') !== 'arguments,name,op') throw Error('command_refused');
    const args = command.arguments;
    if (!args || !Number.isInteger(args.pageId) || args.pageId < 0) throw Error('arguments_refused');
    if (command.name === 'navigate_page') {
      if (args.type !== 'reload') return null;
      if (Object.keys(args).sort().join(',') !== 'pageId,type' || !this.checkpoints.completed || this.reloadReads !== null)
        throw Error('reload_refused');
      this.reloadReads = this.jobReads;
      this.controls.clear();
      return { args, purpose: 'reload' };
    }
    const keys = command.name === 'fill' ? 'fixture,pageId,uid' : 'pageId,uid';
    if (Object.keys(args).sort().join(',') !== keys) throw Error('arguments_refused');
    const control = this.controls.get(args.uid);
    if (!control || control.disabled) throw Error('fresh_control_required');
    if (command.name === 'fill') {
      const empty = control.purpose === 'original' && args.fixture === 'empty'
        && this.checkpoints.login && !this.checkpoints.empty;
      const original = control.purpose === 'original' && args.fixture === 'original' && this.checkpoints.login && !this.checkpoints.original;
      const reviewed = control.purpose === 'draft' && args.fixture === 'reviewed' && this.checkpoints.draft && !this.checkpoints.edited;
      if (!empty && !original && !reviewed) throw Error('fixture_refused');
      this.controls.clear();
      return { args: { pageId: args.pageId, uid: args.uid,
        value: empty ? '' : original ? ORIGINAL : this.edited }, purpose: control.purpose };
    }
    const prerequisites = { login: true, enhance: !!this.checkpoints.original,
      discard: !!this.checkpoints.draft_discard && !this.checkpoints.discarded,
      keep: !!this.checkpoints.draft_keep && !this.checkpoints.kept,
      accept: !!this.checkpoints.edited, generate: !!this.checkpoints.accepted,
      history: !!this.checkpoints.reloaded, job: !!this.checkpoints.history };
    const limits = { login: 1, enhance: 3, discard: 1, keep: 1, accept: 1, generate: 1, history: 1, job: 1 };
    const count = this.clickCounts[control.purpose] ?? 0;
    if (!prerequisites[control.purpose] || count >= (limits[control.purpose] ?? 0)) throw Error('click_refused');
    // Reserve before calling MCP: a timeout is not permission to create a second job.
    this.attempts.add(control.purpose);
    this.clickCounts[control.purpose] = count + 1;
    if (control.purpose === 'job') this.revisitReads = this.jobReads;
    this.controls.clear();
    return { args, purpose: control.purpose };
  }

  async observe(response) {
    const path = new URL(response.url()).pathname;
    const method = response.request().method();
    const status = response.status();
    if (path === '/api/prompts/enhance' && method === 'POST') {
      this.postCounts.enhancement++;
      if (status !== 201) { this.failures.push('enhancement_http_failure'); return; }
      const body = await response.json();
      const sent = JSON.parse(response.request().postData() ?? '{}');
      if (!UUID.test(body.id) || typeof body.enhanced !== 'string' || !body.enhanced.trim() || body.enhanced.length > 12000)
        throw Error('enhancement_response_invalid');
      this.enhancementMatches = sent.prompt === ORIGINAL && body.original === ORIGINAL && body.target_mode === 't2i';
      this.enhancement = { id: body.id, enhanced: body.enhanced };
    } else if (path === '/api/generations' && method === 'POST') {
      this.postCounts.generation++;
      if (status !== 201) { this.failures.push('generation_http_failure'); return; }
      const body = await response.json();
      const sent = JSON.parse(response.request().postData() ?? '{}');
      this.payloadMatches = this.edited !== null && sent.prompt === this.edited && sent.enhancement_id === this.enhancement.id &&
        sent.auto_enhance === false && sent.mode === 't2i' && sent.number_of_images === 1;
      if (!UUID.test(body.id)) throw Error('job_response_invalid');
      this.jobId = body.id;
    } else if (this.jobId && path === `/api/generations/${this.jobId}` && method === 'GET' && status === 200) {
      const body = await response.json();
      this.jobReads++;
      if (body.id !== this.jobId || body.prompt !== this.edited || body.mode !== 't2i') {
        this.failures.push('persisted_job_mismatch'); return;
      }
      if (body.state === 'completed') {
        const asset = body.assets?.[0];
        if (body.assets?.length !== 1 || asset?.kind !== 'image' || asset?.mime !== 'image/png' || !UUID.test(asset?.id))
          throw Error('completed_asset_invalid');
        const assetUrl = new URL(asset.url, 'http://127.0.0.1:18156');
        if (assetUrl.origin !== 'http://127.0.0.1:18156' || !/^\/files\/[0-9a-f-]{36}\/output\.png$/.test(assetUrl.pathname))
          throw Error('asset_url_invalid');
        if (this.assetId && this.assetId !== asset.id) this.failures.push('asset_identity_changed');
        this.jobCompleted = true;
        this.assetId = asset.id;
        this.assetPath = assetUrl.pathname;
      } else if (['failed', 'cancelled'].includes(body.state)) this.failures.push('job_terminal_failure');
    } else if (path === '/api/generations' && method === 'GET' && status === 200) {
      const rows = await response.json();
      this.historyContainsJob = Array.isArray(rows) && rows.some(row => row.id === this.jobId && row.state === 'completed');
    } else if (/^\/files\/[0-9a-f-]{36}\/output\.png$/.test(path) && method === 'GET' && status === 200) {
      const data = Buffer.from(await response.buffer());
      if (data.length > 8 * 1024 * 1024 || !data.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10])))
        throw Error('png_invalid');
      this.fileReads++;
      this.file = { path, bytes: data.length, sha256: createHash('sha256').update(data).digest('hex'),
        mime: response.headers()['content-type']?.split(';')[0] };
    }
  }

  async checkpoint(phase, pageId, call) {
    const expected = { original: ORIGINAL, draft: this.enhancement?.enhanced ?? null, edited: this.edited,
      jobPath: this.jobId ? `/jobs/${this.jobId}` : null, assetPath: this.assetPath, jobId: this.jobId };
    // All comparison inputs remain in memory; the DevTools result contains booleans/numbers only.
    const script = `async () => {
      const x = ${JSON.stringify(expected)};
      const visible = e => !!e && e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0 && getComputedStyle(e).visibility !== 'hidden';
      const main = document.querySelector('.creative-prompt-field textarea');
      const submit = document.querySelector('.creative-composer__actions button[type="submit"]');
      const draft = document.querySelector('[aria-label="편집 가능한 향상 프롬프트 초안"]');
      const image = document.querySelector('img.asset-media');
      let decoded = false;
      if (image) { try { await image.decode(); decoded = true; } catch {} }
      const rows = [...document.querySelectorAll('.history-row')];
      return {
        workspace: location.pathname === '/generate' && visible(document.querySelector('.creative-generate')),
        original: main?.value === x.original,
        draft: x.draft !== null && draft?.value === x.draft && visible(draft),
        edited: x.edited !== null && draft?.value === x.edited && visible(draft),
        accepted: x.edited !== null && main?.value === x.edited && !draft,
        accepted_unedited_draft: x.draft !== null && main?.value === x.draft && !draft,
        review_closed: !draft,
        same_job: x.jobPath !== null && location.pathname === x.jobPath,
        image_decoded: decoded && visible(image) && image.naturalWidth > 0 && image.naturalHeight > 0,
        same_image: !!image && x.assetPath !== null && new URL(image.currentSrc).pathname === x.assetPath,
        width: image?.naturalWidth ?? 0, height: image?.naturalHeight ?? 0,
        history_row: location.pathname === '/history' && rows.some(r => visible(r) && r.querySelector('small[title]')?.getAttribute('title') === x.jobId),
        empty_prompt: location.pathname === '/generate' && main?.value === '',
        empty_submit_found: !!submit,
        empty_disabled: !!submit && submit.disabled
      };
    }`;
    const probe = parseProbe(await call('evaluate_script', { pageId, function: script }));
    const fileMatches = this.file && this.file.path === this.assetPath && this.file.mime === 'image/png';
    const imageOK = probe.same_job && probe.image_decoded && probe.same_image && this.jobCompleted && fileMatches;
    const predicates = {
      login: probe.workspace,
      empty: probe.workspace,
      original: probe.workspace && probe.original,
      draft_discard: probe.original && probe.draft && this.enhancementMatches,
      discarded: probe.original && probe.review_closed && this.clickCounts.discard === 1,
      draft_keep: probe.original && probe.draft && this.enhancementMatches,
      kept: probe.original && probe.review_closed && this.clickCounts.keep === 1,
      draft: probe.original && probe.draft && this.enhancementMatches,
      edited: probe.original && probe.edited,
      accepted: probe.accepted,
      completed: imageOK && this.payloadMatches,
      reloaded: imageOK && this.reloadReads !== null && this.jobReads > this.reloadReads &&
        this.file?.sha256 === this.baseline?.sha256,
      history: probe.history_row && this.historyContainsJob && this.attempts.has('history'),
      revisited: imageOK && this.revisitReads !== null && this.jobReads > this.revisitReads &&
        this.file?.sha256 === this.baseline?.sha256,
    };
    const passed = predicates[phase] === true;
    const result = { phase, passed, ...probe };
    this.steps.push(result);
    if (passed) {
      this.checkpoints[phase] = probe;
      this.lastPhase = phase;
      if (phase === 'completed') this.baseline = { ...this.file };
    }
    return result;
  }

  result() {
    const phases = Object.fromEntries(PHASES.map(phase => [phase, !!this.checkpoints[phase]]));
    const checks = { ...phases, enhancement_payload_matches: this.enhancementMatches,
      accepted_generation_payload_matches: this.payloadMatches,
      three_enhancements: this.postCounts.enhancement === 3, one_generation: this.postCounts.generation === 1,
      no_observation_failures: this.failures.length === 0,
      empty_dom_disabled: this.checkpoints.empty?.empty_disabled === true,
      empty_prompt_confirmed: this.checkpoints.empty?.empty_prompt === true,
      empty_submit_found: this.checkpoints.empty?.empty_submit_found === true,
      empty_accessibility_disabled: this.emptyAccessibilityDisabled === true };
    const technicalComplete = Object.values(phases).every(value => value === true) && this.failures.length === 0;
    return { scenario: 'reviewed_prompt_image', technical_complete: technicalComplete,
      passed: Object.values(checks).every(value => value === true),
      checks, steps: this.steps, post_counts: this.postCounts, job_reads: this.jobReads,
      file_reads: this.fileReads, file: this.file ? { bytes: this.file.bytes, mime: this.file.mime, sha256: this.file.sha256 } : null,
      failures: this.failures };
  }
}

export async function fillWithKeyboard(args, call) {
  await call('click', { pageId: args.pageId, uid: args.uid });
  await call('press_key', { pageId: args.pageId, key: 'Control+A' });
  if (args.value === '') await call('press_key', { pageId: args.pageId, key: 'Backspace' });
  else await call('type_text', { pageId: args.pageId, text: args.value });
  return '';
}
