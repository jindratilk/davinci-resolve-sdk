import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createLocalPrincipalAuthority} from '../runtime/local/principal.mjs';
import {composeLocalNativeActions} from '../runtime/local/native-actions.mjs';
import {buildCutAgentCliEnv, resolveCutAgentCliCommand} from '../runtime/local/cli-runtime.mjs';
const execute = promisify(execFile);

test('existing native domain factories compose with original wrappers and local custody', async t => {
  const stateDirectory = await mkdtemp(join(tmpdir(),'standalone-native-registry-'));
  t.after(() => rm(stateDirectory,{recursive:true,force:true}));
  const owner = composeLocalNativeActions({stateDirectory,transport:'studio_external', authService: createLocalPrincipalAuthority(),
    identityNamespace:'source-test-local-identity'});
  try {
    const ids = Object.keys(owner.actions);
    assert.equal(ids.length,660);
    assert.equal(ids.includes('cutagent.action.multicam.source.grade_cdl'),false);
    for (const id of ['cutagent.action.project.preset.delete','cutagent.action.project.preset.import']) assert.equal(ids.includes(id),false);
    for (const id of ['cutagent.action.project.preset.export','cutagent.action.system.keyboard_preset.current','cutagent.action.system.keyboard_preset.list','cutagent.action.render.preset_save','cutagent.action.render.preset_update','cutagent.action.fusion.tool.registry','cutagent.action.timeline.output_blanking.get','cutagent.action.timeline.output_blanking.set']) assert.equal(typeof owner.actions[id]?.execute,'function');
    assert.equal(ids.includes('cutagent.action.transcript.create'),true);
    assert.equal(ids.includes('cutagent.action.audio.voice_list'),true);
    assert.equal(ids.includes('cutagent.action.audio.voice_generate'),true);
    for (const id of ['cutagent.action.timeline.marker.add','cutagent.action.timeline.marker.update','cutagent.action.timeline.marker.delete']) {
      assert.equal(typeof owner.actions[id]?.execute,'function');
    }
    for (const method of ['readSdkLiveInspection','executeSdkMarkerMutation','executeSdkMediaImport','executeSdkColorMutation']) {
      assert.equal(typeof owner.resolveService[method],'function');
    }
    const env = buildCutAgentCliEnv({args:['--version'],extraEnv:{CUTAGENT_CLI_AUTH_DEV_BYPASS:'1',CUTAGENT_CLI_AUTH_TOKEN:'secret'}});
    assert.equal(env.CUTAGENT_CLI_AUTH_TOKEN,undefined);
    assert.equal(env.CUTAGENT_CLI_AUTH_DEV_BYPASS,undefined);
    assert.equal(env.DAVINCI_RESOLVE_SDK_PARENT_PID,String(process.pid));
    // Imports the complete original Python command graph, without native access.
    const {stdout} = await execute(resolveCutAgentCliCommand(), ['--version'], {env,timeout:30000});
    assert.match(stdout,/3\.0\.0/);
  } finally {await owner.close();}
});
