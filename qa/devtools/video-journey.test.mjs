import test from 'node:test';
import assert from 'node:assert/strict';
import { VideoJourney, videoRoute } from './video-journey.mjs';

test('video routes remove job identity', () => {
  assert.equal(videoRoute('/api/generations/11111111-1111-4111-8111-111111111111'), '/api/generations/{job}');
  assert.equal(videoRoute('/files/11111111-1111-4111-8111-111111111111/output.mp4'), '/files/{job}/output.mp4');
  assert.equal(videoRoute('/private'), null);
});

test('snapshot keeps only scenario controls and fresh disabled state', () => {
  const journey = new VideoJourney();
  const controls = journey.snapshot('uid=1_1 button "텍스트 → 영상"\nuid=1_2 textbox "프롬프트"\n' +
    'uid=1_3 combobox "" value="4s"\nuid=1_4 button "생성" disabled\nuid=1_5 StaticText "private"');
  assert.deepEqual(controls.map(row => row.purpose), ['t2v_mode', 'prompt', 'duration', 'generate']);
  assert.equal(controls.at(-1).disabled, true);
  assert.doesNotMatch(JSON.stringify(controls), /private/);
});

test('incomplete phases cannot pass and policy status remains strict', () => {
  const journey = new VideoJourney();
  assert.equal(journey.result().passed, false);
  journey.checkpoints = { login: {}, mode: {}, empty: {}, allowed_completed: {}, over_limit: {} };
  journey.emptyAccessibilityDisabled = true;
  journey.overLimitStatus = 201;
  assert.equal(journey.result().technical_complete, true);
  assert.equal(journey.result().passed, false);
  journey.overLimitStatus = 403;
  assert.equal(journey.result().passed, true);
});
