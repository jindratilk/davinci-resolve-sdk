import {mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {startNativeLocalRuntime} from '../runtime/index.mjs';
const [transport,statePath]=process.argv.slice(2);
if(!['studio_external','embedded_free'].includes(transport)||!statePath)throw new Error('Usage: node examples/start-runtime.mjs <studio_external|embedded_free> <private-state-directory>');
await mkdir(resolve(statePath),{recursive:true,mode:0o700});
const runtime=await startNativeLocalRuntime({stateDirectory:resolve(statePath),transport});
console.log(JSON.stringify({discoveryFile:runtime.discoveryFile,transport}));
let closing=false;
async function close(){
 if(closing)return;
 closing=true;
 try{await runtime.close();}catch(error){console.error(error);process.exitCode=1;}
}
process.on('SIGINT',close);
process.on('SIGTERM',close);
