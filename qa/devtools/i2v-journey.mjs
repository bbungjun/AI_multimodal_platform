const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PHASES = ['login', 'mode', 'no_source', 'source_selected', 'completed'];

export class I2VJourney {
  constructor(sourceJobId, sourceAssetId) {
    if (!UUID.test(sourceJobId) || !UUID.test(sourceAssetId)) throw Error('source_invalid');
    this.sourceJobId = sourceJobId; this.sourceAssetId = sourceAssetId;
    this.controls = new Map(); this.checkpoints = {}; this.jobId = null;
    this.statePath = []; this.assetMime = null; this.file = null; this.failures = [];
    this.noSourceAccessibilityDisabled = null; this.sourceMatches = false;
  }
  get loginWorkspace() { return this.checkpoints.login?.workspace === true; }
  snapshot(text) {
    this.controls.clear();
    for (const line of text.split('\n')) {
      const match = line.match(/uid=([\d_]+) (button|textbox) "([^"]*)"/);
      if (!match) continue;
      const [, uid, role, name] = match;
      const purpose = name === 'Google로 계속하기' ? 'login' : name === 'I2V' ? 'i2v_mode'
        : name === '모션 프롬프트' ? 'prompt' : name === '생성' ? 'generate'
        : name.includes('I2V 시작') ? 'start_i2v' : null;
      if (purpose) this.controls.set(uid, { uid, role, purpose,
        disabled: /(?:^|\s)disabled(?:\s|$)/.test(line) });
    }
    return [...this.controls.values()];
  }
  prepare(command) {
    if (command.op === 'checkpoint') {
      const fields = command.phase === 'no_source' ? 'accessibility_disabled,op,phase' : 'op,phase';
      if (!PHASES.includes(command.phase) || Object.keys(command).sort().join(',') !== fields)
        throw Error('phase_refused');
      if (command.phase !== PHASES[Object.keys(this.checkpoints).length]) throw Error('phase_order');
      if (command.phase === 'no_source') this.noSourceAccessibilityDisabled = command.accessibility_disabled;
      return { phase: command.phase };
    }
    if (command.op !== 'call' || !['click', 'fill', 'navigate_page'].includes(command.name)) return null;
    const args = command.arguments;
    if (!args || !Number.isInteger(args.pageId)) throw Error('arguments_refused');
    if (command.name === 'navigate_page') {
      if (args.url === 'http://127.0.0.1:18156/login') return null;
      if (args.type !== 'url' || args.url !== `http://127.0.0.1:18156/jobs/${this.sourceJobId}`
          || !this.checkpoints.no_source) throw Error('navigation_refused');
      return { args, purpose: 'source_detail' };
    }
    const control = this.controls.get(args.uid);
    if (!control || control.disabled) throw Error('fresh_control_required');
    if (command.name === 'fill') {
      const value = args.fixture === 'motion' && control.purpose === 'prompt'
        && this.checkpoints.source_selected ? 'A gentle camera move.' : null;
      if (value === null) throw Error('fixture_refused');
      this.controls.clear(); return { args: { pageId: args.pageId, uid: args.uid, value }, purpose: 'prompt' };
    }
    const allowed = control.purpose === 'login' || (control.purpose === 'i2v_mode' && this.checkpoints.login)
      || (control.purpose === 'start_i2v' && this.checkpoints.no_source)
      || (control.purpose === 'generate' && this.checkpoints.source_selected);
    if (!allowed) throw Error('click_refused');
    this.controls.clear(); return { args, purpose: control.purpose };
  }
  async observe(response) {
    const path = new URL(response.url()).pathname, status = response.status();
    if (path === '/api/generations' && response.request().method() === 'POST' && status === 201) {
      const body = await response.json(); if (!UUID.test(body.id)) throw Error('job_invalid'); this.jobId = body.id;
    } else if (this.jobId && path === `/api/generations/${this.jobId}` && status === 200) {
      const body = await response.json();
      this.sourceMatches = body.source_asset_id === this.sourceAssetId;
      const state = body.state === 'pending' ? 'pending' : body.state === 'completed' ? 'completed'
        : ['queued','generating','polling','downloading'].includes(body.state) ? 'running' : null;
      if (state && this.statePath.at(-1) !== state) this.statePath.push(state);
      if (body.state === 'completed') this.assetMime = body.assets?.[0]?.mime ?? null;
    } else if (this.jobId && path === `/files/${this.jobId}/output.mp4` && status === 200) {
      this.file = { mime: response.headers()['content-type']?.split(';')[0], bytes: (await response.buffer()).length };
    }
  }
  async checkpoint(phase, pageId, call) {
    const x = JSON.stringify({ asset: this.sourceAssetId });
    const text = await call('evaluate_script', { pageId, function: `() => { const x=${x};
      const submit=document.querySelector('.creative-composer__actions button[type="submit"]');
      const source=document.querySelector('.creative-source-lock--connected'); const video=document.querySelector('video.asset-media');
      return { workspace:location.pathname==='/generate', disabled:!!submit&&submit.disabled,
        source_selected:!!source&&location.search.includes(x.asset), detail:location.pathname.startsWith('/jobs/'),
        video_visible:!!video&&video.getBoundingClientRect().width>0 }; }` });
    const match=text.match(/```(?:json)?\s*([\s\S]*?)```/); if(!match) throw Error('probe_invalid');
    const p=JSON.parse(match[1]);
    const ok={login:p.workspace,mode:p.workspace,no_source:p.workspace&&p.disabled,
      source_selected:p.workspace&&p.source_selected,completed:p.detail&&this.statePath.at(-1)==='completed'}[phase]===true;
    if(ok)this.checkpoints[phase]=p; return {phase,passed:ok,...p};
  }
  result(){const phases=Object.fromEntries(PHASES.map(p=>[p,!!this.checkpoints[p]]));
    const usable=this.checkpoints.completed?.video_visible===true&&this.file?.bytes>0;
    return {scenario:'i2v_generation',technical_complete:Object.values(phases).every(Boolean),
      passed:Object.values(phases).every(Boolean)&&this.noSourceAccessibilityDisabled===true
        &&this.sourceMatches&&this.assetMime==='video/mp4'&&usable,
      phases,no_source_accessibility_disabled:this.noSourceAccessibilityDisabled,
      source_matches:this.sourceMatches,state_path:this.statePath,asset_mime:this.assetMime,
      usable,file:this.file,failures:this.failures};}
}
