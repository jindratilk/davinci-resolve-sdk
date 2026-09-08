import assert from 'node:assert/strict';
import {mkdtemp,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {randomUUID,createHash} from 'node:crypto';
import {CutAgent,frames,timelineRecordOffset} from 'davinci-resolve-sdk';
import {startNativeLocalRuntime} from '../runtime/index.mjs';
const [transport,projectName,timelineName]=process.argv.slice(2);
if(!['studio_external','embedded_free'].includes(transport)||!projectName||!timelineName)throw new Error('Exact project and timeline required.');
const directory=await mkdtemp(join(tmpdir(),'standalone-marker-live-'));
const label=`Standalone SDK smoke ${randomUUID()}`;
const ignored=new Set(['snapshotId','snapshotRevision','snapshotTrackId','revision','timelineRevision']);
const stable=x=>Array.isArray(x)?x.map(stable):x&&typeof x==='object'?Object.fromEntries(Object.entries(x).filter(([k,v])=>!ignored.has(k)&&typeof v!=='function').map(([k,v])=>[k,stable(v)])):x;
const digest=x=>createHash('sha256').update(JSON.stringify(stable(x))).digest('hex');
let runtime,client,timeline,before;let failure;
const report={directory,label,projectName,timelineName};
console.log(JSON.stringify({phase:'start',directory,label}));
try{
 runtime=await startNativeLocalRuntime({stateDirectory:directory,transport});
 process.env.CUTAGENT_SDK_DISCOVERY_FILE=runtime.discoveryFile;client=await CutAgent.connect();
 const project=await client.projects.current();assert.equal(project.name,projectName);
 timeline=await project.timelines.current();assert.equal(timeline.name,timelineName);
 report.projectId=project.id;report.timelineId=timeline.id;before=await timeline.snapshot();
 report.beforeTracks=digest(before.tracks);report.beforeMarkers=digest(before.markers);
 let offset=0;while(before.markers.some(m=>m.position.value.value===before.start.value.value+offset))offset++;
 const preview=await timeline.markers.previewCreate({position:timelineRecordOffset(before,frames(offset)),name:label,note:'Temporary standalone native validation marker',color:'Blue'});
 const operation=await timeline.markers.create(preview,{idempotencyKey:`idempotency_${randomUUID()}`});
 report.create=await operation.wait();console.log(JSON.stringify({phase:'create_terminal',terminal:report.create}));
 assert.equal(report.create.status,'succeeded');
 const after=await timeline.snapshot();assert.equal(digest(after.tracks),report.beforeTracks);
 const added=after.markers.filter(m=>m.name===label);assert.equal(added.length,1);
 assert.equal(digest(after.markers.filter(m=>m.id!==added[0].id)),report.beforeMarkers);
 report.createdMarkerId=added[0].id;
}catch(error){failure=error;report.failure={name:error.name,message:error.message,failure:error.failure};console.log(JSON.stringify({phase:'failure',...report.failure}));}
finally{
 try{
  if(before&&client&&timeline){
   const project=await client.projects.current();assert.equal(project.name,projectName);assert.equal(project.id,report.projectId);
   const current=await project.timelines.current();assert.equal(current.name,timelineName);assert.equal(current.id,report.timelineId);
   const markers=await timeline.markers.list();const owned=markers.filter(m=>m.name===label);
   assert.ok(owned.length<=1,'Ambiguous smoke marker');
   if(owned.length){
    const preview=await timeline.markers.previewDelete(owned[0]);const operation=await timeline.markers.delete(preview,{idempotencyKey:`idempotency_${randomUUID()}`});
    report.delete=await operation.wait();console.log(JSON.stringify({phase:'delete_terminal',terminal:report.delete}));assert.equal(report.delete.status,'succeeded');
   }
   const restored=await timeline.snapshot();assert.equal(digest(restored.tracks),report.beforeTracks);assert.equal(digest(restored.markers),report.beforeMarkers);report.restored=true;
  }
 }catch(error){report.cleanupFailure={name:error.name,message:error.message,failure:error.failure};failure??=error;console.log(JSON.stringify({phase:'cleanup_failure',...report.cleanupFailure}));}
 await writeFile(join(directory,'smoke-report.json'),JSON.stringify(report,null,2),{mode:0o600});
 await client?.close();await runtime?.close();
 console.log(JSON.stringify({phase:'done',directory,restored:report.restored,success:!failure}));
 if(failure)process.exitCode=1;
}
