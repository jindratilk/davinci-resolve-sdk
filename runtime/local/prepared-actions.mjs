import {resolve,join} from 'node:path';
import {createDesktopSdkPreparedActionComposition} from '../bridge/services/sdk-prepared-action-production-composition.js';
import {createSdkPreparedActionCarrier} from '../bridge/services/sdk-prepared-action-carrier.js';
import {createSdkProjectLibraryDestinationService} from '../bridge/services/sdk-project-library-destination-service.js';
import {createSdkWorkflowOwnershipResolver} from '../bridge/services/sdk-workflow-authority.js';
import {createProfessionalAvPreparedActionBuilderContributions} from '../bridge/services/sdk-professional-av-prepared-action-builders.js';
import {createFusionTimelinePreparedActionBuilderContributions,FUSION_PREPARED_ACTION_IDS,TIMELINE_ARTIFACT_PREPARED_ACTION_IDS,TIMELINE_TOPOLOGY_ACTION_IDS} from '../bridge/services/sdk-fusion-timeline-prepared-action-contributions.js';
import {createColorPreparedActionBuilderContributions,COLOR_SAFE_PREPARED_ACTION_IDS,COLOR_REVIEWED_VISUAL_ARTIFACT_ACTION_IDS} from '../bridge/services/sdk-color-prepared-action-contributions.js';
import {createEditorialProjectPreparedActionBuilderContributions} from '../bridge/services/sdk-editorial-project-prepared-action-contributions.js';
import {createAudioOperationsPreparedActionBuilderContributions} from '../bridge/services/sdk-audio-operations-prepared-action-contributions.js';
import {createFairlightPreparedActionBuilderContributions,FAIRLIGHT_PREPARED_ACTION_IDS} from '../bridge/services/sdk-fairlight-prepared-action-builders.js';
import {createRenderPreparedActionBuilderContributions} from '../bridge/services/sdk-project-render-storage-media-prepared-action-builders.js';

/** Same production builder selections as the upstream composition root. */
export function composeLocalPreparedActions({stateDirectory,authService,...dependencies}) {
  const projectLibraryDestinationService = createSdkProjectLibraryDestinationService({storageDir:join(stateDirectory,'library-destinations'),writableRoots:[stateDirectory]});
  const workflowOwnershipResolver = createSdkWorkflowOwnershipResolver({storageDir:join(stateDirectory,'workflows')});
  const composition = createDesktopSdkPreparedActionComposition({
    ...dependencies, authService, projectLibraryDestinationService,
    resourcesDir:resolve(import.meta.dirname,'../../native'),secretDir:stateDirectory,appVersion:'3.0.0',
    builderContributionFactories:[
      dep => createProfessionalAvPreparedActionBuilderContributions({...dep,enabledActionIds:new Set([
        'cutagent.action.burnin.load','cutagent.action.burnin.preset.export','cutagent.action.burnin.preset.import',
        'cutagent.action.edit.fx.add','cutagent.action.clip.keyframe.add','cutagent.action.clip.transform',
        'cutagent.action.clip.speed_ramp','cutagent.action.system.keyframe_mode.set',
      ])}),
      dep => createFusionTimelinePreparedActionBuilderContributions({...dep,workflowOwnershipResolver,enabledActionIds:new Set([
        ...FUSION_PREPARED_ACTION_IDS,...TIMELINE_ARTIFACT_PREPARED_ACTION_IDS,
        'cutagent.action.version.create','cutagent.action.version.prune','cutagent.action.version.restore',
      ])}),
      dep => createColorPreparedActionBuilderContributions({...dep,enabledActionIds:new Set([...COLOR_SAFE_PREPARED_ACTION_IDS,...COLOR_REVIEWED_VISUAL_ARTIFACT_ACTION_IDS])}),
      dep => createFusionTimelinePreparedActionBuilderContributions({...dep,enabledActionIds:new Set(TIMELINE_TOPOLOGY_ACTION_IDS)}),
      createEditorialProjectPreparedActionBuilderContributions,
      createAudioOperationsPreparedActionBuilderContributions,
      dep => createFairlightPreparedActionBuilderContributions({...dep,artifactCustody:dep.artifactService,enabledActionIds:new Set(FAIRLIGHT_PREPARED_ACTION_IDS)}),
      createRenderPreparedActionBuilderContributions,
    ],
  });
  return createSdkPreparedActionCarrier({...composition, ...dependencies, authService});
}
