import test from 'node:test';
import assert from 'node:assert/strict';
import { VideoJourney, videoRoute } from './video-journey.mjs';
import { I2VJourney } from './i2v-journey.mjs';
import { PipelineJourney, pipelineRoute } from './pipeline-journey.mjs';

test('video routes remove job identity', () => {
  assert.equal(videoRoute('/api/generations/11111111-1111-4111-8111-111111111111'), '/api/generations/{job}');
  assert.equal(videoRoute('/files/11111111-1111-4111-8111-111111111111/output.mp4'), '/files/{job}/output.mp4');
  assert.equal(videoRoute('/private'), null);
});

test('snapshot keeps only scenario controls and fresh disabled state', () => {
  const journey = new VideoJourney();
  const controls = journey.snapshot('uid=1_1 button "T2V"\nuid=1_2 textbox "프롬프트"\n' +
    'uid=1_3 combobox "" value="4s"\nuid=1_4 button "생성" disabled\nuid=1_5 StaticText "private"');
  assert.deepEqual(controls.map(row => row.purpose), ['t2v_mode', 'prompt', 'duration', 'generate']);
  assert.equal(controls.at(-1).disabled, true);
  assert.doesNotMatch(JSON.stringify(controls), /private/);
});

test('incomplete phases cannot pass and policy status remains strict', () => {
  const journey = new VideoJourney();
  assert.equal(journey.result().passed, false);
  journey.checkpoints = { login: {}, mode: {}, empty: {},
    allowed_completed: { video_visible: true }, over_limit: {} };
  journey.emptyAccessibilityDisabled = true;
  journey.file = { mime: 'video/mp4', bytes: 1 };
  journey.overLimitStatus = 201;
  assert.equal(journey.result().technical_complete, true);
  assert.equal(journey.result().passed, false);
  journey.overLimitStatus = 403;
  assert.equal(journey.result().passed, true);
});

test('initial login navigation stays on the common auth seam', () => {
  const journey = new VideoJourney();
  assert.equal(journey.prepare({ op: 'call', name: 'navigate_page', arguments: {
    pageId: 0, type: 'url', url: 'http://127.0.0.1:18156/login'
  } }), null);
});

const SOURCE_JOB = '11111111-1111-4111-8111-111111111111';
const SOURCE_ASSET = '22222222-2222-4222-8222-222222222222';
test('I2V source ids are required and never appear in controls', () => {
  assert.throws(() => new I2VJourney('bad', SOURCE_ASSET));
  const journey = new I2VJourney(SOURCE_JOB, SOURCE_ASSET);
  const controls = journey.snapshot('uid=1_1 button "I2V"\nuid=1_2 button "이 이미지로 I2V 시작"');
  assert.deepEqual(controls.map(row => row.purpose), ['i2v_mode', 'start_i2v']);
  assert.doesNotMatch(JSON.stringify(controls), /11111111|22222222/);
});

test('I2V completion requires source mime and usable result', () => {
  const journey = new I2VJourney(SOURCE_JOB, SOURCE_ASSET);
  journey.checkpoints = {login:{}, mode:{}, no_source:{}, source_selected:{}, completed:{video_visible:true}};
  journey.noSourceAccessibilityDisabled = true; journey.sourceMatches = true;
  journey.assetMime = 'video/mp4'; journey.file = {bytes:1, mime:'video/mp4'};
  assert.equal(journey.result().passed, true); journey.sourceMatches = false;
  assert.equal(journey.result().passed, false);
});

test('pipeline routes redact parent identity', () => {
  assert.equal(pipelineRoute('/api/pipelines/11111111-1111-4111-8111-111111111111'),
    '/api/pipelines/{parent}');
  assert.equal(pipelineRoute('/private'), null);
});

test('pipeline completion requires identity source and both terminals', () => {
  const journey = new PipelineJourney();
  journey.checkpoints = {login:{}, mode:{}, incomplete:{}, submitted:{}, completed:{}, reloaded:{}};
  journey.incompleteAccessibilityDisabled = true; journey.sameIdentity = true; journey.sourceLinked = true;
  journey.parentStates = ['pending','running','completed'];
  journey.childStates = ['blocked','pending','running','completed'];
  assert.equal(journey.result().passed, true); journey.sourceLinked = false;
  assert.equal(journey.result().passed, false);
});
