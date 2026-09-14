import test from'node:test';import assert from'node:assert/strict';import{WorkspaceJourney,workspaceRoute}from'./workspace-journey.mjs';const J='11111111-1111-4111-8111-111111111111';
import { MasterJourney } from './master-journey.mjs';
test('workspace routes redact retry identity',()=>{assert.equal(workspaceRoute(`/api/generations/${J}/retry`),'/api/generations/{job}/retry');assert.equal(workspaceRoute('/private'),null)});
test('controls do not retain row identity',()=>{const j=new WorkspaceJourney(J);const c=j.snapshot(`uid=1_1 button "fixture 작업 ${J.slice(0,8)}"\nuid=1_2 link "기록 8"`);assert.deepEqual(c.map(x=>x.purpose),['retry_row','history']);assert.doesNotMatch(JSON.stringify(c),/11111111/)});
test('master result requires all six observed phases',()=>{const j=new MasterJourney();j.checkpoints={login:{},navigation:{},overview:{},users:{},audit:{},ops:{}};assert.equal(j.result().passed,true);delete j.checkpoints.audit;assert.equal(j.result().passed,false)});
