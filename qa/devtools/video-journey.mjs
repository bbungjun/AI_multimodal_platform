const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PHASES = ['login', 'mode', 'empty', 'allowed_completed', 'over_limit'];

export function videoRoute(path) {
  if (path === '/api/generations') return path;
  if (/^\/api\/generations\/[0-9a-f-]{36}$/.test(path)) return '/api/generations/{job}';
  if (/^\/files\/[0-9a-f-]{36}\/output\.mp4$/.test(path)) return '/files/{job}/output.mp4';
  return null;
}

export class VideoJourney {
  constructor() {
    this.controls = new Map();
    this.checkpoints = {};
    this.postCount = 0;
    this.jobId = null;
    this.statePath = [];
    this.file = null;
    this.overLimitStatus = 0;
    this.failures = [];
    this.emptyAccessibilityDisabled = null;
    this.generateClicks = 0;
  }

  get loginWorkspace() { return this.checkpoints.login?.workspace === true; }

  snapshot(text) {
    this.controls.clear();
    for (const line of text.split('\n')) {
      const match = line.match(/uid=([\d_]+) (button|textbox|combobox) "([^"]*)"/);
      if (!match) continue;
      const [, uid, role, name] = match;
      let purpose = name === 'Google로 계속하기' ? 'login'
        : name === 'T2V' ? 't2v_mode'
        : name === '프롬프트' ? 'prompt'
        : name === '생성' ? 'generate' : null;
      if (role === 'combobox' && /value="4s"/.test(line)) purpose = 'duration';
      if (!purpose) continue;
      this.controls.set(uid, { uid, role, purpose,
        disabled: /(?:^|\s)disabled(?:\s|$)/.test(line) });
    }
    return [...this.controls.values()];
  }

  prepare(command) {
    if (command.op === 'checkpoint') {
      const fields = command.phase === 'empty' ? 'accessibility_disabled,op,phase' : 'op,phase';
      if (!PHASES.includes(command.phase) || Object.keys(command).sort().join(',') !== fields
          || (command.phase === 'empty' && typeof command.accessibility_disabled !== 'boolean'))
        throw Error('phase_refused');
      if (command.phase !== PHASES[Object.keys(this.checkpoints).length]) throw Error('phase_order');
      if (command.phase === 'empty') this.emptyAccessibilityDisabled = command.accessibility_disabled;
      return { phase: command.phase };
    }
    if (command.op !== 'call' || !['click', 'fill', 'navigate_page'].includes(command.name)) return null;
    const args = command.arguments;
    if (!args || !Number.isInteger(args.pageId)) throw Error('arguments_refused');
    if (command.name === 'navigate_page') {
      if (args.type === 'url' && args.url === 'http://127.0.0.1:18156/login') return null;
      if (Object.keys(args).sort().join(',') !== 'pageId,type,url' || args.type !== 'url'
          || args.url !== 'http://127.0.0.1:18156/generate?mode=t2v'
          || !this.checkpoints.allowed_completed) throw Error('navigation_refused');
      this.controls.clear();
      return { args, purpose: 'boundary_return' };
    }
    if (typeof args.uid !== 'string') throw Error('arguments_refused');
    const control = this.controls.get(args.uid);
    if (!control || control.disabled) throw Error('fresh_control_required');
    if (command.name === 'fill') {
      if (Object.keys(args).sort().join(',') !== 'fixture,pageId,uid') throw Error('arguments_refused');
      const values = {
        empty: control.purpose === 'prompt' && this.checkpoints.mode ? '' : null,
        video: control.purpose === 'prompt' && this.checkpoints.empty ? 'A slow camera move across a studio table.' : null,
        long: control.purpose === 'duration' && this.checkpoints.allowed_completed ? '6s' : null,
      };
      if (!(args.fixture in values) || values[args.fixture] === null) throw Error('fixture_refused');
      this.controls.clear();
      return { args: { pageId: args.pageId, uid: args.uid, value: values[args.fixture] },
        purpose: control.purpose };
    }
    if (Object.keys(args).sort().join(',') !== 'pageId,uid') throw Error('arguments_refused');
    const allowed = (control.purpose === 'login' && !this.checkpoints.login)
      || (control.purpose === 't2v_mode' && this.checkpoints.login && !this.checkpoints.mode)
      || (control.purpose === 'generate' && (this.checkpoints.empty || this.checkpoints.allowed_completed));
    if (!allowed) throw Error('click_refused');
    if (control.purpose === 'generate' && ++this.generateClicks > 2) throw Error('click_refused');
    this.controls.clear();
    return { args, purpose: control.purpose };
  }

  async observe(response) {
    const path = new URL(response.url()).pathname;
    const method = response.request().method();
    const status = response.status();
    if (path === '/api/generations' && method === 'POST') {
      this.postCount++;
      if (this.postCount === 2) { this.overLimitStatus = status; return; }
      if (status !== 201) { this.failures.push('allowed_generation_http'); return; }
      const body = await response.json();
      if (!UUID.test(body.id)) throw Error('job_invalid');
      this.jobId = body.id;
    } else if (this.jobId && path === `/api/generations/${this.jobId}` && status === 200) {
      const body = await response.json();
      const state = body.state === 'pending' ? 'pending' : body.state === 'completed' ? 'completed'
        : ['queued', 'generating', 'polling', 'downloading'].includes(body.state) ? 'running' : null;
      if (state && this.statePath.at(-1) !== state) this.statePath.push(state);
      if (body.state === 'completed') {
        const asset = body.assets?.[0];
        if (asset?.mime !== 'video/mp4') this.failures.push('video_asset_invalid');
      }
    } else if (this.jobId && path === `/files/${this.jobId}/output.mp4` && status === 200) {
      const bytes = Buffer.from(await response.buffer());
      this.file = { mime: response.headers()['content-type']?.split(';')[0], bytes: bytes.length };
    }
  }

  async checkpoint(phase, pageId, call) {
    const text = await call('evaluate_script', { pageId, function: `() => {
      const submit = document.querySelector('.creative-composer__actions button[type="submit"]');
      const prompt = document.querySelector('.creative-prompt-field textarea');
      const video = document.querySelector('video.asset-media');
      return { workspace: location.pathname === '/generate', mode: !!document.querySelector('[aria-label="생성 모드"]'),
        empty: prompt?.value === '', disabled: !!submit && submit.disabled,
        detail: location.pathname.startsWith('/jobs/'), video_visible: !!video && video.getBoundingClientRect().width > 0 };
    }` });
    const match = text.match(/```(?:json)?\s*([\s\S]*?)```/);
    if (!match) throw Error('probe_invalid');
    const probe = JSON.parse(match[1]);
    const predicates = {
      login: probe.workspace,
      mode: probe.workspace && probe.mode,
      empty: probe.workspace && probe.empty,
      allowed_completed: probe.detail && this.statePath.at(-1) === 'completed',
      over_limit: [201, 403].includes(this.overLimitStatus),
    };
    const passed = predicates[phase] === true;
    if (passed) this.checkpoints[phase] = {...probe};
    return { phase, passed, ...probe };
  }

  result() {
    const phases = Object.fromEntries(PHASES.map(phase => [phase, !!this.checkpoints[phase]]));
    const product = { empty_disabled: this.emptyAccessibilityDisabled === true,
      asset_mime: this.file?.mime === 'video/mp4',
      outcome_usable: this.checkpoints.allowed_completed?.video_visible === true && this.file?.bytes > 0 };
    return { scenario: 't2v_generation', technical_complete: Object.values(phases).every(Boolean),
      passed: Object.values(phases).every(Boolean) && this.overLimitStatus === 403
        && Object.values(product).every(Boolean) && this.failures.length === 0,
      phases, post_count: this.postCount, state_path: this.statePath,
      over_limit_status: this.overLimitStatus, empty_accessibility_disabled: this.emptyAccessibilityDisabled,
      product, file: this.file, failures: this.failures };
  }
}
