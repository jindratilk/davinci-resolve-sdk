import {CutAgent, artifactId, idempotencyKey, type ProjectId} from 'cutagent';
import {ActionIds} from 'cutagent/actions';
import {ProjectIdSchema} from 'cutagent/schemas';
const client=await CutAgent.connect();
const project=await client.projects.current();
const id:ProjectId=project.id;
const presetExport=await client.actions.start('cutagent.action.project.preset.export',{
  name:'Editorial',destinationArtifactId:artifactId('artifact_project_preset_export_type_smoke'),
},{idempotencyKey:idempotencyKey()});
const presetTerminal=await presetExport.wait();
if(presetTerminal.status==='succeeded') client.artifacts.open(presetTerminal.result.payload.data.artifact);
void id; void idempotencyKey; void ActionIds; void ProjectIdSchema;
await client.close();
