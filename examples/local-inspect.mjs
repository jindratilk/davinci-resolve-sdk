import {mkdtemp, chmod, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {CutAgent} from 'davinci-resolve-sdk';
import {startLocalRuntime} from '../runtime/index.mjs';
import {createNativeInspectionOwner} from '../runtime/local/native-inspection.mjs';
const transport=process.argv[2];
if (!['studio_external','embedded_free'].includes(transport)) throw new Error('Pass studio_external or embedded_free explicitly.');
const stateDirectory=await mkdtemp(join(tmpdir(),'standalone-sdk-'));
await chmod(stateDirectory,0o700);
let runtime, client;
try {
  const owner=createNativeInspectionOwner({python:resolve(import.meta.dirname,'../.venv/bin/python'),transport});
  runtime=await startLocalRuntime({stateDirectory,...owner,identityNamespace:'standalone-local'});
  process.env.CUTAGENT_SDK_DISCOVERY_FILE=runtime.discoveryFile;
  client=await CutAgent.connect();
  const project=await client.projects.current();
  console.log(JSON.stringify({projectId:project.id,name:project.name}));
} finally {
  try { await client?.close(); } finally {
    await runtime?.close();
    await rm(stateDirectory,{recursive:true,force:true});
  }
}
