import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {CutAgent} from '../sdk/dist/index.js';
import {startNativeLocalRuntime} from '../runtime/index.mjs';

test('SDK AI service actions direct users to the CutAgent desktop app without external work',async t=>{
  const directory=await mkdtemp(join(tmpdir(),'cutagent-sdk-ai-service-'));
  const previous=process.env.CUTAGENT_SDK_DISCOVERY_FILE;
  const runtime=await startNativeLocalRuntime({stateDirectory:directory,transport:'studio_external'});
  process.env.CUTAGENT_SDK_DISCOVERY_FILE=runtime.discoveryFile;
  let client;
  t.after(async()=>{await client?.close();await runtime.close();if(previous===undefined)delete process.env.CUTAGENT_SDK_DISCOVERY_FILE;else process.env.CUTAGENT_SDK_DISCOVERY_FILE=previous;await rm(directory,{recursive:true,force:true});});
  client=await CutAgent.connect();
  const verify=failure=>{assert.equal(failure.code,'SUBSCRIPTION_REQUIRED');assert.match(failure.message,/CutAgent desktop app/);assert.match(failure.message,/https:\/\/cutagent\.ai/);assert.equal(failure.possibleMutation,'none');assert.equal(failure.usage,'not_reserved');};
  const voices=await client.actions.lowLevel.read('cutagent.action.audio.voice_list',{});const voicesTerminal=await voices.wait();assert.equal(voicesTerminal.status,'failed');verify(voicesTerminal.failure);
  for(const [actionId,input] of [
    ['cutagent.action.audio.voice_generate',{text:'must remain local',voiceId:'unsubmitted'}],
    ['cutagent.action.transcript.create',{projectId:'project_local',timelineId:'timeline_local',precondition:'revision_local',diarize:false,keyterms:[],verbatim:false,newJob:true}],
  ]){
    const operation=await client.actions.invoke(actionId,input,{idempotencyKey:`idempotency_${randomUUID()}`});
    const terminal=await operation.wait();assert.equal(terminal.status,'failed');verify(terminal.failure);assert.equal(terminal.possibleMutation,'none');assert.equal(terminal.usage,'not_reserved');
  }
});
