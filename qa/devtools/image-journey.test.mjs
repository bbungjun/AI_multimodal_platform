import test from 'node:test';
import assert from 'node:assert/strict';
import { ImageJourney, ORIGINAL, imageRoute } from './image-journey.mjs';

const JOB = '11111111-1111-4111-8111-111111111111';
const ENH = '22222222-2222-4222-8222-222222222222';
const ASSET = '33333333-3333-4333-8333-333333333333';
const PNG = Buffer.from([137,80,78,71,13,10,26,10,0,1]);
const response = (path, method, body, sent = {}, status = 200) => ({
  url: () => 'http://127.0.0.1:18156' + path, status: () => status,
  request: () => ({ method: () => method, postData: () => JSON.stringify(sent) }),
  json: async () => body, buffer: async () => PNG, headers: () => ({ 'content-type': 'image/png' }),
});
const probeCall = value => async () => '```json\n' + JSON.stringify(value) + '\n```';
const phaseCommand = phase => ({ op: 'checkpoint', phase });
async function phase(journey, name, probe) {
  journey.prepare(phaseCommand(name));
  return journey.checkpoint(name, 1, probeCall(probe));
}
async function prepareJob(journey, wrongPrompt = false) {
  await journey.observe(response('/api/prompts/enhance', 'POST', { id: ENH, original: ORIGINAL, enhanced: 'draft', target_mode: 't2i' },
    { prompt: ORIGINAL }, 201));
  await journey.observe(response('/api/generations', 'POST', { id: JOB }, {
    mode: 't2i', prompt: wrongPrompt ? ORIGINAL : journey.edited, auto_enhance: false,
    number_of_images: 1, enhancement_id: ENH,
  }, 201));
  await journey.observe(response(`/api/generations/${JOB}`, 'GET', {
    id: JOB, prompt: journey.edited, mode: 't2i', state: 'completed',
    assets: [{ id: ASSET, kind: 'image', mime: 'image/png', url: `/files/${JOB}/output.png` }],
  }));
  await journey.observe(response(`/files/${JOB}/output.png`, 'GET', null));
}

test('snapshot drops prompt/identity and retains only usable scenario controls', () => {
  const journey = new ImageJourney();
  journey.jobId = JOB;
  const controls = journey.snapshot(`uid=1_1 textbox "프롬프트" value="private original"\n` +
    `uid=1_2 button "생성" disabled\nuid=1_3 button "완료 private original 작업 11111111"\n` +
    `uid=1_4 button "person@example.test"\nuid=1_5 link "기록 8"`);
  assert.deepEqual(controls.map(c => c.purpose), ['original', 'generate', 'job', 'history']);
  assert.equal(controls[1].disabled, true);
  assert.doesNotMatch(JSON.stringify(controls), /private|example\.test|11111111/);
});

test('fixture writes need fresh controls and phase, generation cannot be retried blindly', () => {
  const journey = new ImageJourney();
  journey.checkpoints.login = { workspace: true };
  journey.snapshot('uid=1_1 textbox "프롬프트"');
  const fill = { op: 'call', name: 'fill', arguments: { pageId: 1, uid: '1_1', fixture: 'original' } };
  assert.equal(journey.prepare(fill).args.value, ORIGINAL);
  assert.throws(() => journey.prepare(fill));
  journey.checkpoints.accepted = {};
  journey.snapshot('uid=2_1 button "생성"');
  const click = { op: 'call', name: 'click', arguments: { pageId: 1, uid: '2_1' } };
  journey.prepare(click);
  journey.snapshot('uid=2_1 button "생성"');
  assert.throws(() => journey.prepare(click));
});

test('phase ordering, arbitrary values and non-scenario controls are refused', () => {
  const journey = new ImageJourney();
  assert.throws(() => journey.prepare(phaseCommand('completed')));
  assert.throws(() => journey.prepare({ op: 'checkpoint', phase: 'login', hidden: true }));
  journey.snapshot('uid=1_1 textbox "프롬프트"\nuid=1_2 button "삭제"');
  assert.throws(() => journey.prepare({ op: 'call', name: 'fill', arguments: { pageId: 1, uid: '1_1', value: 'arbitrary' } }));
  assert.throws(() => journey.prepare({ op: 'call', name: 'click', arguments: { pageId: 1, uid: '1_2' } }));
});

test('wrong accepted payload cannot pass even when completed image is visible', async () => {
  const journey = new ImageJourney();
  await prepareJob(journey, true);
  const step = await journey.checkpoint('completed', 1, probeCall({ same_job: true, image_decoded: true, same_image: true }));
  assert.equal(step.passed, false);
  assert.equal(journey.result().checks.accepted_generation_payload_matches, false);
});

test('missing decode, wrong image, wrong job and unobserved response cannot pass', async () => {
  for (const key of ['same_job', 'image_decoded', 'same_image']) {
    const journey = new ImageJourney();
    await prepareJob(journey);
    assert.equal((await journey.checkpoint('completed', 1, probeCall({ same_job: true, image_decoded: true, same_image: true, [key]: false }))).passed, false);
  }
  const journey = new ImageJourney();
  assert.equal((await journey.checkpoint('completed', 1, probeCall({ same_job: true, image_decoded: true, same_image: true }))).passed, false);
});

test('full ordered proof needs new job reads on reload/revisit and no duplicate POST', async () => {
  const journey = new ImageJourney();
  await phase(journey, 'login', { workspace: true });
  await phase(journey, 'original', { workspace: true, original: true });
  await prepareJob(journey);
  await phase(journey, 'draft', { original: true, draft: true });
  await phase(journey, 'edited', { original: true, edited: true });
  await phase(journey, 'accepted', { accepted: true });
  const image = { same_job: true, image_decoded: true, same_image: true, width: 640, height: 360 };
  await phase(journey, 'completed', image);
  journey.prepare({ op: 'call', name: 'navigate_page', arguments: { pageId: 1, type: 'reload' } });
  assert.equal((await phase(journey, 'reloaded', image)).passed, false);
  journey.jobReads++;
  assert.equal((await phase(journey, 'reloaded', image)).passed, true);
  journey.attempts.add('history');
  await journey.observe(response('/api/generations', 'GET', [{ id: JOB, state: 'completed' }]));
  await phase(journey, 'history', { history_row: true });
  journey.snapshot(`uid=3_1 button "完了 작업 ${JOB.slice(0,8)}"`);
  journey.prepare({ op: 'call', name: 'click', arguments: { pageId: 1, uid: '3_1' } });
  assert.equal((await phase(journey, 'revisited', image)).passed, false);
  journey.jobReads++;
  await phase(journey, 'revisited', image);
  assert.equal(journey.result().passed, true);
  assert.doesNotMatch(JSON.stringify(journey.result()), /11111111|22222222|33333333|small blue|soft light/);
  journey.postCounts.generation++;
  assert.equal(journey.result().passed, false);
});

test('normalized routes and failed HTTP remain distinct from successful jobs', async () => {
  assert.equal(imageRoute(`/api/generations/${JOB}`), '/api/generations/{job}');
  assert.equal(imageRoute(`/files/${JOB}/output.png`), '/files/{job}/output.png');
  assert.equal(imageRoute('/api/auth/me'), null);
  const journey = new ImageJourney();
  await journey.observe(response('/api/generations', 'POST', {}, {}, 402));
  assert.deepEqual(journey.result().failures, ['generation_http_failure']);
  assert.equal(journey.result().passed, false);
});
