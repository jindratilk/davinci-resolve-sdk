import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {configureLocalCliRuntime} from '../runtime/local/cli-runtime.mjs';
import {createSdkPreparedActionRuntimeClient} from '../runtime/bridge/services/sdk-prepared-action-runtime-client.js';
import {startNativeLocalRuntime} from '../runtime/index.mjs';
import {CutAgent} from '../sdk/dist/index.js';

test('existing full native prepared registry initializes through owned local pipes', async t => {
  const directory=await mkdtemp(join(tmpdir(),'local-native-host-'));
  t.after(()=>rm(directory,{recursive:true,force:true}));
  configureLocalCliRuntime({transport:'studio_external'});
  let client;
  try {
    client=await createSdkPreparedActionRuntimeClient({
      executablePath:resolve(import.meta.dirname,'../native/framed_prepared_host'),
      initialization:{runtimeContext:{localPrincipal:{fingerprint:'source-test'}},custodyDatabasePath:join(directory,'custody.sqlite3')},
      redeemAuthorization:async()=>{throw new Error('Commercial redemption must not run.');},
      assertProtectedState:async()=>false,
    });
    assert.equal(client.advertisedActionIds.length,517);
    assert.equal(client.hasAction('cutagent.action.timeline.marker.add'),true);
    assert.equal(client.hasAction('cutagent.action.clip.speed_ramp'),true);
    for (const id of ['cutagent.action.render.preset_save','cutagent.action.render.preset_update','cutagent.action.fusion.tool.registry','cutagent.action.timeline.output_blanking.get','cutagent.action.timeline.output_blanking.set']) assert.equal(client.hasAction(id),true);
  } finally {await client?.close();}
});

test('original SDK connects to combined native and workflow owners without native inspection', async t => {
  const stateDirectory=await mkdtemp(join(tmpdir(),'local-native-sdk-'));
  const previous=process.env.CUTAGENT_SDK_DISCOVERY_FILE;
  let runtime,client;
  try {
    runtime=await startNativeLocalRuntime({stateDirectory,transport:'studio_external'});
    process.env.CUTAGENT_SDK_DISCOVERY_FILE=runtime.discoveryFile;
    client=await CutAgent.connect();
    assert.equal(client.connection.descriptor.distribution,'standalone_local');
    assert.equal(typeof client.actions.start,'function');
  } finally {
    await client?.close();await runtime?.close();await rm(stateDirectory,{recursive:true,force:true});
    if(previous===undefined)delete process.env.CUTAGENT_SDK_DISCOVERY_FILE;else process.env.CUTAGENT_SDK_DISCOVERY_FILE=previous;
  }
});
