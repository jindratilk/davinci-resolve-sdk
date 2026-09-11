import {z} from 'zod';
import {sdkTranscriptCreateInputSchema,sdkVoiceGenerateInputSchema,sdkVoiceGenerateResultSchema} from '../bridge/contracts/generated/sdk-operations.js';

const landingPage='https://cutagent.ai';
const services=Object.freeze({
  'cutagent.action.audio.voice_list':Object.freeze({label:'AI voice generation',inputSchema:z.object({}).strict(),resultSchema:z.unknown(),idempotency:'optional'}),
  'cutagent.action.audio.voice_generate':Object.freeze({label:'AI voice generation',inputSchema:sdkVoiceGenerateInputSchema,resultSchema:sdkVoiceGenerateResultSchema,idempotency:'required'}),
  'cutagent.action.transcript.create':Object.freeze({label:'AI transcription',inputSchema:sdkTranscriptCreateInputSchema,resultSchema:z.unknown(),idempotency:'required'}),
});

function failure(label,context){
  const message=`${label} is available in the CutAgent desktop app. Explore plans: ${landingPage}.`;
  return {status:'failed',possibleMutation:'none',usage:'not_reserved',failure:{
    kind:'subscription_required',code:'SUBSCRIPTION_REQUIRED',message,retrySafe:false,
    possibleMutation:'none',usage:'not_reserved',recovery:['contact_support'],
    recoveryGuidance:[`Explore the CutAgent desktop app at ${landingPage}.`],readbackRequired:false,
    ...(context?.requestId?{requestId:context.requestId}:{}),
    ...(context?.operationId?{operationId:context.operationId}:{}),
    ...(context?.executionId?{executionId:context.executionId}:{}),
  }};
}

/** Local package boundary for AI services provided by the CutAgent desktop app. */
export function createDesktopAppServiceActions(){
  return Object.freeze(Object.fromEntries(Object.entries(services).map(([actionId,service])=>[actionId,Object.freeze({
    inputSchema:service.inputSchema,resultSchema:service.resultSchema,idempotency:service.idempotency,
    execute(context){return failure(service.label,context);},
    reconcile(context){return failure(service.label,context);},
  })])));
}
