import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {createConstraintScopeRepo} from '../bridge/repos/constraint-scope-repo.js';
import {createMutationPolicyGate} from '../bridge/services/mutation-policy/mutation-policy-gate.js';
import {createSdkDirectMutationPolicyAuthority} from '../bridge/services/sdk-direct-mutation-policy-authority.js';
import {createCutAgentCliAuthorizationService} from '../bridge/services/cutagent-cli-authorization.js';
import {createResolveService} from '../bridge/services/resolve-service.js';
import {createSdkLiveInspectionService} from '../bridge/services/sdk-live-inspection-service.js';
import {createSdkArtifactService} from '../bridge/services/sdk-artifact-service.js';
import {createColorAssetService} from '../bridge/services/color-asset-service.js';
import {mergeSdkActionRegistries} from '../bridge/services/sdk-action-registry.js';
import {createSdkRenderActionDefinitions} from '../bridge/services/sdk-render-action-service.js';
import {createSdkCaptionActionDefinitions} from '../bridge/services/sdk-caption-actions.js';
import {createSdkFusionGraphAction, CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID} from '../bridge/services/sdk-fusion-graph-action.js';
import {composeLocalPreparedActions} from './prepared-actions.mjs';
import {createSdkWorkflowAuthority} from '../bridge/services/sdk-workflow-authority.js';
import {createVersionCheckpointService} from '../bridge/services/version-checkpoint-service.js';
import {configureLocalCliRuntime} from './cli-runtime.mjs';
import {createSdkMarkerActions} from '../bridge/services/sdk-marker-action-service.js';
import {createSdkTimelineItemMoveActions} from '../bridge/services/sdk-timeline-item-move-service.js';
import {createSdkTimelineBladeActions} from '../bridge/services/sdk-timeline-blade-service.js';
import {createSdkTimelineStructureActions} from '../bridge/services/sdk-timeline-structure-action-service.js';
import {createSdkColorActions} from '../bridge/services/sdk-color-action-service.js';
import {createSdkTimelineEditActions} from '../bridge/services/sdk-timeline-edit-action-service.js';
import {createSdkMulticamActions} from '../bridge/services/sdk-multicam-action-service.js';
import {createSdkProjectMediaActions} from '../bridge/services/sdk-project-media-action-service.js';
import {createSdkStorageActions} from '../bridge/services/sdk-storage-action-service.js';
import {createSdkInventoryActions} from '../bridge/services/sdk-inventory-action-service.js';
import {createSdkLowLevelActions} from '../bridge/services/sdk-low-level-action-service.js';

/** Existing native factories share their original policy, wrappers and projections. */
export function composeLocalNativeActions({stateDirectory, transport, authService, sdkRuntimeService, identityNamespace}) {
  configureLocalCliRuntime({transport});
  const embeddedFree = transport === 'embedded_free';
  const settingsService = {
    getRuntimeMode: () => 'standalone_local',
    getAppSettings: () => ({non_secret_runtime_preferences: {
      cutagent_cli_timeout_seconds: embeddedFree ? 300 : 180,
      managed_workspace_root: stateDirectory,
    }}),
  };
  const repo = createConstraintScopeRepo({storageDir: join(stateDirectory, 'constraints')});
  const mutationPolicyGate = createMutationPolicyGate({repo, signedExecutionScopeAvailable: true});
  const directMutationPolicyAuthority = createSdkDirectMutationPolicyAuthority({sdkRuntimeService, mutationPolicyGate});
  const cutAgentCliAuthorizationService = createCutAgentCliAuthorizationService({settingsService, authService, mutationPolicyGate});
  const resolveService = createResolveService({settingsService, cutAgentCliAuthorizationService});
  // Free's serialized Lua spool can take longer than the external Studio
  // transport to collect a complete Timeline snapshot. Keep each protected
  // inspection bounded by the CLI's published 180-second maximum while
  // retaining the normal 60-second deadline for Studio.
  const liveInspectionService = createSdkLiveInspectionService({
    resolveService,
    identityNamespace,
    defaultInternalInspectionTimeoutMs: embeddedFree ? 180_000 : 60_000,
  });
  const artifactService = createSdkArtifactService({storageDir: join(stateDirectory, 'artifacts'), managedRenderRoot: join(stateDirectory, 'renders')});
  const colorAssetService = createColorAssetService({storageDir: join(stateDirectory, 'color-assets'), settingsService, authService});
  const dependencies = {resolveService, liveInspectionService, mutationPolicyGate, directMutationPolicyAuthority,
    artifactService, colorAssetService, storageDir: join(stateDirectory, 'storage-recovery')};
  const toolExecutionService = {executeCutAgentCliCommand({args}, options = {}) {
    for (const guard of [options.mutationGuard, options.sdkTimelineGuard]) {
      if (guard !== undefined && !/^sha256:[a-f0-9]{64}$/.test(guard)) throw new TypeError('Invalid native mutation guard.');
    }
    return resolveService.executeLocalSdkCommand(args, {...options, carrier: 'sdk',
      extraEnv: {...(options.extraEnv ?? {}),
        ...(options.mutationGuard ? {CUTAGENT_SDK_MUTATION_GUARD: options.mutationGuard} : {}),
        ...(options.sdkTimelineGuard ? {CUTAGENT_SDK_TIMELINE_GUARD: options.sdkTimelineGuard} : {})}});
  }};
  const registry = JSON.parse(readFileSync(new URL('../../native/cutagent_cli/public_reference/fusion-registry.json', import.meta.url), 'utf8'));
  const prepared = composeLocalPreparedActions({...dependencies,stateDirectory,authService});
  const actions = mergeSdkActionRegistries([
    {owner: 'prepared', actions: prepared.actions},
    {owner: 'render', actions: createSdkRenderActionDefinitions({...dependencies, toolExecutionService, managedRenderRoot: join(stateDirectory, 'renders')})},
    {owner: 'captions', actions: Object.fromEntries(Object.entries(createSdkCaptionActionDefinitions({...dependencies, toolExecutionService, authService, transcriptDeliveryDir: join(stateDirectory, 'transcripts')})).filter(([id]) => id !== 'cutagent.action.transcript.create'))},
    {owner: 'fusion', actions: {[CUTAGENT_SDK_FUSION_GRAPH_ACTION_ID]: createSdkFusionGraphAction({...dependencies, expectedRegistryDigest: registry.registryDigest})}},
    {owner: 'marker-action', actions: createSdkMarkerActions({...dependencies,activatedActionIds:['cutagent.action.timeline.marker.update','cutagent.action.timeline.marker.delete']})},
    {owner: 'timeline-item-move', actions: createSdkTimelineItemMoveActions(dependencies)},
    {owner: 'timeline-blade', actions: createSdkTimelineBladeActions(dependencies)},
    {owner: 'timeline-structure-action', actions: createSdkTimelineStructureActions(dependencies)},
    {owner: 'color-action', actions: createSdkColorActions(dependencies)},
    {owner: 'timeline-edit-action', actions: createSdkTimelineEditActions(dependencies)},
    {owner: 'multicam-action', actions: createSdkMulticamActions(dependencies)},
    {owner: 'project-media-action', actions: createSdkProjectMediaActions(dependencies)},
    {owner: 'storage-action', actions: createSdkStorageActions(dependencies)},
    {owner: 'inventory-action', actions: createSdkInventoryActions(dependencies)},
    {owner: 'low-level-action', actions: createSdkLowLevelActions({...dependencies, excludedActionIds: ['cutagent.action.audio.voice_list']})},
  ]);
  return Object.freeze({actions, resolveService, liveInspectionService, sdkArtifactService: artifactService,
    identityNamespace, mutationPolicyGate, directMutationPolicyAuthority,
    composeWorkflowAuthority(operationAuthority) {
      const checkpointService = createVersionCheckpointService({settingsService,checkpointDir:join(stateDirectory,'checkpoints'),cutAgentCliAuthorizationService});
      const workflow = createSdkWorkflowAuthority({...dependencies,operationAuthority,checkpointService,storageDir:join(stateDirectory,'workflows')});
      directMutationPolicyAuthority.bindWorkflowScopeResolver(request => workflow.resolveStepScope(request));
      return workflow;
    },
    async close() {await prepared.close(); artifactService.stop();}});
}
