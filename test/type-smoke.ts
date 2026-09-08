import {CutAgent, idempotencyKey, type ProjectId} from 'davinci-resolve-sdk';
import {ActionIds} from 'davinci-resolve-sdk/actions';
import {ProjectIdSchema} from 'davinci-resolve-sdk/schemas';
const client=await CutAgent.connect();
const project=await client.projects.current();
const id:ProjectId=project.id;
void id; void idempotencyKey; void ActionIds; void ProjectIdSchema;
await client.close();
