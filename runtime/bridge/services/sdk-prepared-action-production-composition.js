import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {createSdkPreparedActionRuntimeClient} from "./sdk-prepared-action-runtime-client.js";
import {createSdkPreparedActionBuilderContribution} from "./sdk-prepared-action-carrier.js";
import {captureAuthenticatedSdkRequest} from "./sdk-authenticated-request.js";
import {preparedActionDigest} from "./sdk-prepared-action-digest.js";
import {
  CUTAGENT_PREPARED_ACTION_CAPABILITY_DIGEST,
  CUTAGENT_PREPARED_ACTION_CONTRACT_DIGEST,
  CUTAGENT_PREPARED_ACTION_KERNEL_DIGEST,
  CUTAGENT_PREPARED_ACTION_PROTOCOL_VERSION,
} from "../contracts/generated/sdk-prepared-action.js";
import {CUTAGENT_SDK_API_VERSION, CUTAGENT_SDK_WIRE_PROTOCOL} from "../contracts/generated/sdk-runtime.js";
import {CUTAGENT_SDK_PROTOCOL_DIGEST} from "../contracts/generated/sdk-runtime-protocol.js";
import {CUTAGENT_PLUGIN_CARRIER_PROTOCOL_DIGEST} from "../contracts/generated/sdk-plugin-runtime-protocol.js";
import {sdkMarkerCreateInputSchema} from "../contracts/generated/sdk-operations.js";
import {CUTAGENT_PREPARED_ACTION_ACTION_METADATA} from "../contracts/sdk-prepared-action-metadata.generated.js";

export const SDK_PREPARED_MARKER_ADD_ACTION_ID = "cutagent.action.timeline.marker.add";

const SESSION_HOST_PROTOCOL_DIGEST = "sha256:2581a58d7361bb3d22a0d39b31c8f2ca2c1bc4d7442cc508a8dbcb1c4f57ebd4";
const PRIVATE_BINDING_MAX_COUNT = 128;
const PRIVATE_BINDING_TTL_MS = 5 * 60_000;


function sha256(bytes) { return crypto.createHash("sha256").update(bytes).digest("hex"); }
export function preparedRuntimeFingerprint(manifestDigest) {
  if (!/^[a-f0-9]{64}$/.test(manifestDigest)) throw new TypeError("Prepared-action runtime manifest digest is invalid.");
  return `runtime_fingerprint_f${manifestDigest.slice(0, 42)}`;
}
export function releaseProjectLibraryDestinationReservation(projectLibraryDestinationService, binding) {
  const destination = binding?.privateContext?.projectLibraryDestination;
  if (!destination) return false;
  projectLibraryDestinationService?.settleTerminal({
    operationId: destination.operationId,
    accountFingerprint: destination.accountFingerprint,
    terminal: {status: "failed"},
  });
  return true;
}
function fairlightDigest(value) {
  return `sha256:${sha256(Buffer.from(JSON.stringify(value)))}`;
}

export function createFairlightReadResolver({request, captured, liveInspectionService}) {
  const privateBinding = captured.privateContext?.fairlight;
  if (!request.actionId.startsWith("cutagent.action.fairlight.")
    && request.actionId !== "cutagent.action.sdk.fairlight.plan.apply") return null;
  if (!privateBinding || !Array.isArray(privateBinding.targets)) {
    throw new Error("Prepared Fairlight read lacks private target custody.");
  }
  if (CUTAGENT_PREPARED_ACTION_ACTION_METADATA[request.actionId]?.operationClass === "mutation") {
    if (typeof liveInspectionService?.resolveFairlightPreparedTargets !== "function") {
      throw new Error("Prepared Fairlight mutation lacks its live verification authority.");
    }
    return (payload, callbackContext) => liveInspectionService.resolveFairlightPreparedTargets(payload, {
      ...callbackContext,
      privateFairlightBinding: privateBinding,
    });
  }
  return async (payload, callbackContext) => {
    if (callbackContext.originalRequest.actionId !== request.actionId
      || payload?.actionId !== request.actionId
      || payload?.scope?.projectId !== request.identities.projectId
      || payload?.scope?.timelineId !== request.identities.timelineId
      || payload?.scope?.projectRevision !== request.revisions.project
      || payload?.scope?.timelineRevision !== request.revisions.timeline
      || !Array.isArray(payload.targets)
      || payload.targets.length !== privateBinding.targets.length) {
      throw new Error("Prepared Fairlight live callback drifted from its signed request.");
    }
    const inspected = await liveInspectionService.readWithMutationGuard({
      operation: "timeline.snapshot",
      projectId: request.identities.projectId,
      timelineId: request.identities.timelineId,
    });
    const snapshot = inspected.value;
    if (snapshot?.project?.id !== request.identities.projectId
      || snapshot?.timeline?.id !== request.identities.timelineId
      || snapshot?.revision !== request.revisions.timeline) {
      throw new Error("Prepared Fairlight read timeline revision changed.");
    }
    const tracks = Array.isArray(snapshot.tracks) ? snapshot.tracks : [];
    const resolved = payload.targets.map((target, index) => {
      const locator = privateBinding.targets[index];
      if (target.stableId !== locator?.stableId
        || target.revision !== request.revisions.targets[target.stableId]) {
        throw new Error("Prepared Fairlight target identity or revision changed.");
      }
      if (target.kind === "project") {
        if (target.stableId !== request.identities.projectId) {
          throw new Error("Prepared Fairlight project target changed.");
        }
        return {...target, exists: true};
      }
      if (target.kind === "track") {
        const matches = tracks.filter((track) => track.snapshotId === target.stableId
          && track.snapshotRevision === target.revision);
        if (matches.length !== 1) throw new Error("Prepared Fairlight track target is stale.");
        const track = matches[0];
        return {...target, exists: true, trackIndex: track.index, trackName: track.name};
      }
      if (target.kind !== "clip") throw new Error("Prepared Fairlight target kind is not admitted.");
      const matches = tracks.flatMap((track) => (track.clips ?? []).map((clip) => ({track, clip})))
        .filter(({clip}) => clip.id === target.stableId && clip.snapshotRevision === target.revision);
      if (matches.length !== 1) throw new Error("Prepared Fairlight clip target is stale.");
      const {track, clip} = matches[0];
      return {
        ...target,
        exists: true,
        nativeId: locator.nativeId,
        trackIndex: track.index,
        trackName: track.name,
        clipName: clip.name,
        recordStartFrame: clip.recordRange.start,
        recordEndFrameExclusive: clip.recordRange.endExclusive,
      };
    });
    const clip = resolved.length === 1 && resolved[0].kind === "clip" ? {
      timelineId: request.identities.timelineId,
      timelineItemId: resolved[0].stableId,
      clipName: resolved[0].clipName,
      trackIndex: resolved[0].trackIndex,
      range: {
        recordStartFrame: resolved[0].recordStartFrame,
        recordEndFrame: resolved[0].recordEndFrameExclusive,
        durationFrames: resolved[0].recordEndFrameExclusive - resolved[0].recordStartFrame,
        sourceStartFrame: privateBinding.targets[0].sourceStartFrame,
        sourceEndFrame: privateBinding.targets[0].sourceEndFrameExclusive,
      },
    } : undefined;
    const snapshotProof = {
      revision: snapshot.revision,
      digest: fairlightDigest({timelineId: request.identities.timelineId, revision: snapshot.revision, resolved}),
      ...(clip ? {clip} : {}),
    };
    const response = {
      contractVersion: 1,
      actionId: request.actionId,
      phase: payload.phase,
      scope: payload.scope,
      targets: resolved,
      snapshot: snapshotProof,
      protectedState: {status: "read_only", digest: snapshotProof.digest},
      handlerOverrides: {},
    };
    if (payload.phase === "verify") {
      return {
        ...response,
        outcome: "passed",
        protectedStatePreserved: true,
        evidence: [{
          modality: "structural",
          digest: snapshotProof.digest,
          summary: `Fresh exact ${request.actionId} target readback matched the signed timeline revision.`,
        }],
      };
    }
    if (!["prepare", "current"].includes(payload.phase)) {
      throw new Error("Prepared Fairlight read callback phase is not admitted.");
    }
    return response;
  };
}
function artifactEntry(manifest, name) {
  const entry = manifest?.entries?.find((candidate) => candidate?.path === name);
  if (entry?.kind !== "file" || !Number.isSafeInteger(entry.size) || !/^[a-f0-9]{64}$/.test(entry.sha256 ?? "")) {
    throw new Error(`Prepared-action packaged manifest omitted ${name}.`);
  }
  return entry;
}

export function serializePrivateTimelineItemNativeIds(inspected) {
  const entries = inspected?.privateTimelineItemNativeIdByPublicId;
  if (!(entries instanceof Map)) {
    throw new Error("Prepared-action private inspection omitted native timeline-item custody.");
  }
  for (const [publicId, nativeId] of entries) {
    if (typeof publicId !== "string" || !publicId || typeof nativeId !== "string" || !nativeId) {
      throw new Error("Prepared-action private inspection contains invalid native timeline-item custody.");
    }
  }
  return Object.fromEntries(entries);
}

async function readPreparedFusionCompositions(liveInspectionService, request) {
  const value = await liveInspectionService.read(request);
  return {operation: request.operation, value};
}

/** Private desktop composition for the signed prepared-action carrier. */
export function createDesktopSdkPreparedActionComposition({
  resourcesDir,
  secretDir,
  appVersion,
  authService,
  cutagentCloudService,
  liveInspectionService,
  artifactService,
  projectLibraryDestinationService,
  resolveService,
  sdkRuntimeService = null,
  builderContributionFactories = [],
  createPreparedActionRuntimeClient = createSdkPreparedActionRuntimeClient,
  onRuntimeCallbackError = null,
  evaluatorRuntimeEnvironmentAuthority = null,
} = {}) {
  if (typeof resourcesDir !== "string" || !path.isAbsolute(resourcesDir) || typeof secretDir !== "string" || !path.isAbsolute(secretDir)) throw new TypeError("Local prepared runtime roots are required.");
  const runtimeRoot = resourcesDir;
  const executablePath = path.join(runtimeRoot, "framed_prepared_host");
  const manifestBytes = fs.readFileSync(path.join(runtimeRoot, "SOURCE_INVENTORY.json"));
  const manifestDigest = sha256(manifestBytes);
  const manifest = {version: appVersion};
  const hostEntry = {sha256: sha256(fs.readFileSync(executablePath))};
  const runtimeEntry = {sha256: sha256(fs.readFileSync(path.join(runtimeRoot, "cutagent")))};
  const desktopArtifactDigest = manifestDigest;
  const capturedRuntimeBindings = new Map();
  const cleanupPrivateInput = (binding) => {
    const inputPath = binding?.privateContext?.timelineTopology?.inputFile?.absolutePath;
    if (typeof inputPath !== "string") return;
    const stagingRoot = path.resolve(secretDir, "sdk-timeline-inputs");
    const resolved = path.resolve(inputPath);
    if (path.dirname(resolved) !== stagingRoot) throw new Error("Prepared-action private input escaped its staging root.");
    fs.rmSync(resolved, {force: true});
  };
  const releasePrivateRuntimeBinding = (operationId) => {
    const entry = capturedRuntimeBindings.get(operationId);
    if (!entry) return;
    clearTimeout(entry.timer);
    capturedRuntimeBindings.delete(operationId);
    releaseProjectLibraryDestinationReservation(projectLibraryDestinationService, entry.binding);
    cleanupPrivateInput(entry.binding);
  };
  const capturePrivateRuntimeBinding = async (binding) => {
    const encoded = Buffer.from(JSON.stringify(binding), "utf8");
    if (encoded.length > 1024 * 1024) throw new TypeError("Prepared-action private runtime binding exceeded its bound.");
    releasePrivateRuntimeBinding(binding.operationId);
    if (capturedRuntimeBindings.size >= PRIVATE_BINDING_MAX_COUNT) {
      throw new Error("Prepared-action private runtime binding custody is full.");
    }
    const timer = setTimeout(() => releasePrivateRuntimeBinding(binding.operationId), PRIVATE_BINDING_TTL_MS);
    timer.unref?.();
    capturedRuntimeBindings.set(binding.operationId, {
      binding: Object.freeze(JSON.parse(encoded.toString("utf8"))),
      timer,
    });
  };
  const takePrivateRuntimeBinding = (operationId) => {
    const entry = capturedRuntimeBindings.get(operationId);
    if (!entry) return null;
    clearTimeout(entry.timer);
    capturedRuntimeBindings.delete(operationId);
    return entry.binding;
  };

  const scopedMarkerState = ({context, input}) => sdkRuntimeService?.readExecutionTimelineState?.({
    sessionId: context.sdkSessionId,
    accountFingerprint: context.accountFingerprint,
    projectId: input.projectId,
    timelineId: input.timelineId,
    timelineRevision: input.timelineRevision,
  }) ?? null;
  const markerBinding = (projectBefore, inspectedTimeline, projectAfter, input) => {
      const timeline = inspectedTimeline.value;
      const projectLibraryId = projectBefore.privateExecutionIdentity?.projectLibraryId;
      const projectLibraryRevision = projectBefore.mutationGuard;
      const projectRevision = projectBefore.value?.projectRevision?.revision;
      if (typeof projectLibraryId !== "string" || !projectLibraryId
        || projectBefore.value?.project?.id !== input.projectId
        || projectBefore.value?.timeline?.id !== input.timelineId
        || projectAfter.privateExecutionIdentity?.projectLibraryId !== projectLibraryId
        || projectAfter.mutationGuard !== projectLibraryRevision
        || projectAfter.value?.project?.id !== input.projectId
        || projectAfter.value?.timeline?.id !== input.timelineId
        || projectAfter.value?.projectRevision?.revision !== projectRevision
        || timeline.project?.id !== input.projectId
        || timeline.timeline?.id !== input.timelineId
        || timeline.revision !== input.timelineRevision) {
        throw new Error("Prepared-action live project binding changed during composition.");
      }
      const binding = Object.freeze({
        projectLibraryId,
        projectLibraryRevision,
        projectId: input.projectId,
        projectRevision,
        timelineId: input.timelineId,
        timelineRevision: timeline.revision,
        mutationGuard: inspectedTimeline.mutationGuard,
      });
      return binding;
  };
  const captureMarkerBinding = async ({context, input}) => {
      const scoped = scopedMarkerState({context, input});
      if (scoped) return markerBinding(scoped.projectContext, scoped.timeline, scoped.projectContext, input);
      const projectBefore = await liveInspectionService.readWithMutationGuard({operation: "project.context"});
      const inspectedTimeline = await liveInspectionService.readWithMutationGuard({operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId});
      const projectAfter = await liveInspectionService.readWithMutationGuard({operation: "project.context"});
      return markerBinding(projectBefore, inspectedTimeline, projectAfter, input);
  };

  const markerContribution = createSdkPreparedActionBuilderContribution({
    inputSchema: sdkMarkerCreateInputSchema,
    mutationBinding: Object.freeze({minimumBinding: "project+timeline", referencedPayloadDigests: Object.freeze([])}),
    async captureRequestBinding({context, input}) {
      const binding = await captureMarkerBinding({
        context,
        input: structuredClone(input),
      });
      if (binding?.projectId !== input.projectId
        || binding?.timelineId !== input.timelineId
        || binding?.timelineRevision !== input.timelineRevision) {
        throw new Error("Prepared marker live identity capture drifted from the accepted target.");
      }
      return {
        identities: {projectLibraryId: binding.projectLibraryId, projectId: binding.projectId, timelineId: binding.timelineId, targetIds: [binding.timelineId]},
        revisions: {projectLibrary: binding.projectLibraryRevision, project: binding.projectRevision, timeline: binding.timelineRevision, targets: {[binding.timelineId]: binding.timelineRevision}},
        privateContext: {timeline: {mutationGuard: binding.mutationGuard}},
      };
    },
  });
  if (!Array.isArray(builderContributionFactories) || builderContributionFactories.some((factory) => typeof factory !== "function")) {
    throw new TypeError("Prepared-action domain contribution factories must be functions.");
  }
  const builderContributions = {[SDK_PREPARED_MARKER_ADD_ACTION_ID]: markerContribution};
  for (const factory of builderContributionFactories) {
    const packet = factory(Object.freeze({
      liveInspectionService,
      artifactService,
      projectLibraryDestinationService,
      resolveService,
      secretDir,
    }));
    if (!packet || typeof packet !== "object" || Array.isArray(packet)) {
      throw new TypeError("Prepared-action domain contribution factory returned an invalid packet.");
    }
    for (const [actionId, contribution] of Object.entries(packet)) {
      if (Object.hasOwn(builderContributions, actionId)) throw new Error(`Prepared-action domain contribution collides: ${actionId}`);
      builderContributions[actionId] = contribution;
    }
  }

  return Object.freeze({
    builderContributions: Object.freeze(builderContributions),
    capturePrivateRuntimeBinding,
    releasePrivateRuntimeBinding,
    async runtimeClientFactory({request, authenticated, sdkSessionId, advertisedActionIds, resolveLiveTargets = null, terminalRecovery = false}) {
      if (!sdkSessionId) throw new Error("Local prepared session is unavailable.");
      authService.assertCurrent(authenticated);
      const issuedAt = Date.now();
      const captured = takePrivateRuntimeBinding(request.operationId) ?? (terminalRecovery ? {
        executionId: request.executionId,
        identities: request.identities,
        revisions: request.revisions,
        privateContext: {},
      } : null);
      if (!captured || captured.executionId !== request.executionId
        || preparedActionDigest("prepared-runtime-identities", captured.identities) !== preparedActionDigest("prepared-runtime-identities", request.identities)
        || preparedActionDigest("prepared-runtime-revisions", captured.revisions) !== preparedActionDigest("prepared-runtime-revisions", request.revisions)) {
        throw new Error("Prepared-action exact private runtime binding is unavailable.");
      }
      const privateProjectBinding = captured.privateContext?.project ?? null;
      if (privateProjectBinding !== null && (
        !privateProjectBinding || typeof privateProjectBinding !== "object" || Array.isArray(privateProjectBinding)
        || JSON.stringify(Object.keys(privateProjectBinding).sort()) !== JSON.stringify(["nativeProjectId", "nativeProjectLibrary"])
        || typeof privateProjectBinding.nativeProjectId !== "string" || !privateProjectBinding.nativeProjectId
        || !privateProjectBinding.nativeProjectLibrary || typeof privateProjectBinding.nativeProjectLibrary !== "object"
      )) {
        throw new Error("Prepared-action private project binding is malformed.");
      }
      const runtimeFingerprint = preparedRuntimeFingerprint(manifestDigest);
      const runtimeContext = {
        localPrincipal: {fingerprint: authenticated.accountFingerprint},
        session: {
          sessionId: sdkSessionId,
          preparedActionKernelDigest: CUTAGENT_PREPARED_ACTION_KERNEL_DIGEST,
          preparedActionContractDigest: CUTAGENT_PREPARED_ACTION_CONTRACT_DIGEST,
          preparedActionCapabilityDigest: CUTAGENT_PREPARED_ACTION_CAPABILITY_DIGEST,
        },
        project: {
          projectLibraryId: request.identities.projectLibraryId,
          projectLibraryRevision: request.revisions.projectLibrary,
          projectId: request.identities.projectId,
          projectRevision: request.revisions.project,
          ...(privateProjectBinding ?? {}),
        },
        timeline: request.identities.timelineId ? {
          projectId: request.identities.projectId,
          timelineId: request.identities.timelineId,
          timelineRevision: request.revisions.timeline,
          ...(captured.privateContext?.timeline?.mutationGuard ? {
            mutationGuard: captured.privateContext.timeline.mutationGuard,
            privateInspectionCallback: true,
          } : {}),
        } : {projectId: request.identities.projectId, timelineId: null, timelineRevision: null},
        privateBindings: captured.privateContext,
        artifacts: {
          protocol: {protocolVersion: 1, protocolDigest: CUTAGENT_SDK_PROTOCOL_DIGEST, preparedActionKernelDigest: CUTAGENT_PREPARED_ACTION_KERNEL_DIGEST},
          app: {artifactKind: "app", version: appVersion, sha256: desktopArtifactDigest},
          runtime: {artifactKind: "runtime", version: manifest.version, sha256: hostEntry.sha256},
          cli: {artifactKind: "cli", version: manifest.version, sha256: runtimeEntry.sha256},
          runtimeManifestDigest: `sha256:${manifestDigest}`,
        },
      };
      const fairlightReadResolver = createFairlightReadResolver({request, captured, liveInspectionService});
      const admittedLiveResolver = fairlightReadResolver ?? resolveLiveTargets;
      let runtime;
      try {
        runtime = await createPreparedActionRuntimeClient({
        executablePath,
        resourcesDir,
        initialization: {
          runtimeContext,
          custodyDatabasePath: path.join(secretDir, "sdk-operation-store", "prepared-action-custody.sqlite3"),
          advertisedActionIds,
        },
        runtimeEnv: {
          CUTAGENT_CHECKPOINT_DIR: path.join(secretDir, "checkpoints"),
          ...(authService?.isSdkFinalEvaluator === true ? {
            ...authService.preparedActionEvaluatorRuntimeEnv(),
            ...(evaluatorRuntimeEnvironmentAuthority?.runtimeEnvironment({accountFingerprint: authenticated.accountFingerprint, sessionId: sdkSessionId, actionId: request.actionId}) ?? {}),
          } : {}),
        },
        privateEvaluatorDiagnostics: authService?.isSdkFinalEvaluator === true,
        onCallbackError: onRuntimeCallbackError,
        originalRequest: request,
        async redeemAuthorization() { throw new Error("Commercial redemption is unavailable in the local host."); },
        async inspectPreparedActionTimeline(payload) {
          const inspectionPhase = payload?.phase ?? "current";
          if (!["current", "verify"].includes(inspectionPhase)) {
            throw new Error("Prepared-action private inspection phase is not admitted.");
          }
          const newTimelineResult = ["cutagent.action.edit.ripple_delete", "cutagent.action.edit.from_edl"].includes(request.actionId)
            && payload?.operation === `${request.actionId.slice("cutagent.action.".length)}.result`;
          if (payload?.projectId !== request.identities.projectId || (!newTimelineResult && payload?.timelineId !== request.identities.timelineId)) {
            throw new Error("Prepared-action private inspection target drifted.");
          }
          const operation = payload.operation ?? "timeline.snapshot";
          if (newTimelineResult) {
            const current = await liveInspectionService.readWithMutationGuard({operation: "timeline.current", projectId: request.identities.projectId});
            if (current.value?.name !== payload.expectedTimelineName || typeof current.value?.id !== "string"
              || current.value.id === request.identities.timelineId) {
              throw new Error("Prepared Edit result timeline is missing, ambiguous, or not newly created.");
            }
            const inspected = await liveInspectionService.readWithMutationGuard({operation: "timeline.snapshot", projectId: request.identities.projectId, timelineId: current.value.id});
            if (request.actionId === "cutagent.action.edit.from_edl") {
              const original = await liveInspectionService.readWithMutationGuard({
                operation: "timeline.snapshot", projectId: request.identities.projectId,
                timelineId: request.identities.timelineId,
              });
              return {snapshot: inspected.value, mutationGuard: inspected.mutationGuard, originalSnapshot: original.value};
            }
            return {snapshot: inspected.value, mutationGuard: inspected.mutationGuard};
          }
          if (operation === "clip.marker.list") {
            const exactTarget = captured.privateContext?.exactTimelineItemTarget;
            if (!exactTarget || typeof exactTarget.id !== "string" || !exactTarget.id) {
              throw new Error("Prepared-action marker inspection lacks exact private target custody.");
            }
            const value = await resolveService.executeSdkLowLevelAction({
              actionId: "cutagent.action.clip.marker.list",
              input: payload.input ?? {},
            }, {
              extraEnv: {CUTAGENT_SDK_EXPECTED_CLIP_MOTION_TARGET: JSON.stringify(exactTarget)},
            });
            return {operation, value};
          }
          if (operation === "fusion.compositions") {
            return readPreparedFusionCompositions(liveInspectionService, {
              operation,
              projectId: request.identities.projectId,
              timelineId: request.identities.timelineId,
              timelineItemId: payload.timelineItemId,
              expectedRevision: inspectionPhase === "current" ? request.revisions.timeline : null,
            });
          }
          if (operation !== "timeline.snapshot") {
            throw new Error("Prepared-action private inspection operation is not admitted.");
          }
          if (inspectionPhase === "current") {
            const scoped = sdkRuntimeService?.readExecutionTimelineState?.({
              sessionId: sdkSessionId,
              accountFingerprint: authenticated.accountFingerprint,
              projectId: request.identities.projectId,
              timelineId: request.identities.timelineId,
              timelineRevision: request.revisions.timeline,
            });
            if (scoped) {
              return {
                snapshot: scoped.timeline.value,
                mutationGuard: scoped.timeline.mutationGuard,
                projectBinding: {
                  projectLibraryId: scoped.projectContext.privateExecutionIdentity.projectLibraryId,
                  projectLibraryRevision: scoped.projectContext.mutationGuard,
                  projectId: scoped.projectContext.value.project.id,
                  projectRevision: scoped.projectContext.value.projectRevision.revision,
                },
                privateTimelineItemNativeIds: serializePrivateTimelineItemNativeIds(scoped.timeline),
              };
            }
          }
          const projectBefore = await liveInspectionService.readWithMutationGuard({operation: "project.context"});
          if (inspectionPhase === "current" && (
            projectBefore.privateExecutionIdentity?.projectLibraryId !== request.identities.projectLibraryId
            || projectBefore.value?.project?.id !== request.identities.projectId
          )) {
            throw Object.assign(new Error("Prepared-action live project binding changed before private timeline inspection."), {
              code: "STALE_REVISION",
            });
          }
          const inspected = await liveInspectionService.readWithMutationGuard({
            operation: "timeline.snapshot",
            projectId: request.identities.projectId,
            timelineId: request.identities.timelineId,
          });
          const projectAfter = await liveInspectionService.readWithMutationGuard({operation: "project.context"});
          const projectBinding = {
            projectLibraryId: projectBefore.privateExecutionIdentity?.projectLibraryId,
            projectLibraryRevision: projectBefore.mutationGuard,
            projectId: projectBefore.value?.project?.id,
            projectRevision: projectBefore.value?.projectRevision?.revision,
          };
          const snapshotTimelineId = inspected.value?.timeline?.id ?? inspected.value?.timelineId;
          const requiresSignedRevision = inspectionPhase === "current";
          if (projectBinding.projectLibraryId !== request.identities.projectLibraryId
            || projectBinding.projectId !== request.identities.projectId
            || inspected.value?.project?.id !== request.identities.projectId
            || snapshotTimelineId !== request.identities.timelineId
            || projectAfter.privateExecutionIdentity?.projectLibraryId !== projectBinding.projectLibraryId
            || projectAfter.mutationGuard !== projectBinding.projectLibraryRevision
            || projectAfter.value?.project?.id !== projectBinding.projectId
            || projectAfter.value?.projectRevision?.revision !== projectBinding.projectRevision
            || (requiresSignedRevision && (
              projectBinding.projectLibraryRevision !== request.revisions.projectLibrary
              || projectBinding.projectRevision !== request.revisions.project
            ))) {
            throw new Error("Prepared-action live project binding changed during private inspection.");
          }
          if (inspectionPhase === "verify") {
            sdkRuntimeService?.captureExecutionProjectContext?.({
              sessionId: sdkSessionId,
              accountFingerprint: authenticated.accountFingerprint,
              inspected: projectAfter,
            });
            sdkRuntimeService?.captureExecutionTimelineState?.({
              sessionId: sdkSessionId,
              accountFingerprint: authenticated.accountFingerprint,
              inspected,
            });
          }
          return {
            snapshot: inspected.value,
            mutationGuard: inspected.mutationGuard,
            projectBinding,
            privateTimelineItemNativeIds: serializePrivateTimelineItemNativeIds(inspected),
          };
        },
        ...(admittedLiveResolver ? {
          resolveLiveTargets: admittedLiveResolver,
        } : {}),
        });
      } catch (error) {
        releaseProjectLibraryDestinationReservation(projectLibraryDestinationService, captured);
        cleanupPrivateInput(captured);
        throw error;
      }
      return Object.freeze({
        ...runtime,
        async execute(payload) {
          if (request.actionId.startsWith("cutagent.action.media.")) {
            liveInspectionService.invalidateMediaPoolSnapshots?.(request.identities.projectId);
          }
          try { return await runtime.execute(payload); } finally { cleanupPrivateInput(captured); }
        },
        async revoke(payload) {
          try { return await runtime.revoke(payload); } finally {
            releaseProjectLibraryDestinationReservation(projectLibraryDestinationService, captured);
            cleanupPrivateInput(captured);
          }
        },
        async releasePreDispatchReservations() {
          releaseProjectLibraryDestinationReservation(projectLibraryDestinationService, captured);
        },
        async close() {
          try { return await runtime.close?.(); } finally { cleanupPrivateInput(captured); }
        },
        async publishTerminalArtifacts(terminal) {
          projectLibraryDestinationService?.settleTerminal({
            operationId: request.operationId,
            accountFingerprint: authenticated.accountFingerprint,
            terminal,
          });
          if (terminal?.status !== "succeeded") return;
          if (terminal?.verification?.outcome !== "passed") throw new Error("Prepared-action output cannot publish without passed verification.");
          artifactService.publishPrivateOutputArtifacts({
            operationId: request.operationId,
            accountFingerprint: authenticated.accountFingerprint,
            publicResult: terminal?.result?.value,
          });
        },
      });
    },
  });
}
