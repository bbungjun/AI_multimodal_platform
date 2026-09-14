import test from 'node:test';
import assert from 'node:assert/strict';
import { controlUid, pageId } from './image-controller.mjs';

test('controller uses only a fresh enabled purpose control', () => {
  const message = { controls: [
    { uid: '1_1', purpose: 'generate', disabled: true },
    { uid: '1_2', purpose: 'generate', disabled: false },
  ] };
  assert.equal(controlUid(message, 'generate'), '1_2');
  assert.equal(controlUid(message, 'other'), null);
});

test('controller parses bounded page ids without URLs', () => {
  assert.equal(pageId({ pages: '0: about:blank [selected]' }), 0);
  assert.throws(() => pageId({ pages: 'private' }));
});
