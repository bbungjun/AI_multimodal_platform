import test from 'node:test'; import assert from 'node:assert/strict'; import {I2VJourney} from './i2v-journey.mjs';
const J='11111111-1111-4111-8111-111111111111',A='22222222-2222-4222-8222-222222222222';
test('source ids are required and never appear in controls',()=>{assert.throws(()=>new I2VJourney('bad',A));
 const j=new I2VJourney(J,A); const c=j.snapshot('uid=1_1 button "I2V"\nuid=1_2 button "이 이미지로 I2V 시작"');
 assert.deepEqual(c.map(x=>x.purpose),['i2v_mode','start_i2v']); assert.doesNotMatch(JSON.stringify(c),/11111111|22222222/);});
test('complete phases still require source mime and usable result',()=>{const j=new I2VJourney(J,A);
 j.checkpoints={login:{},mode:{},no_source:{},source_selected:{},completed:{video_visible:true}};
 j.noSourceAccessibilityDisabled=true;j.sourceMatches=true;j.assetMime='video/mp4';j.file={bytes:1,mime:'video/mp4'};
 assert.equal(j.result().passed,true);j.sourceMatches=false;assert.equal(j.result().passed,false);});
