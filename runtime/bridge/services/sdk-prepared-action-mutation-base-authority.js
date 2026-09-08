import {sdkPreparedActionMutationBaseSchema} from "../contracts/generated/sdk-prepared-action.js";
import {CUTAGENT_PREPARED_ACTION_ACTION_METADATA} from "../contracts/sdk-prepared-action-metadata.generated.js";
import {mutationPolicyDigest, PRIVATE_IMPACT_REGISTRY_DIGEST} from "./mutation-policy/impact-lowering.js";

const RANK = Object.freeze({"account/project-library": 1, project: 2, "project+timeline": 3});

function exactScopeBinding(scope, request, minimumBinding) {
  const binding = scope.binding;
  return binding.level === minimumBinding
    && binding.projectLibraryId === request.identities.projectLibraryId
    && (minimumBinding === "account/project-library" || (
      binding.projectId === request.identities.projectId
      && binding.projectRevision === request.revisions.project
    ))
    && (minimumBinding !== "project+timeline" || (
      binding.timelineId === request.identities.timelineId
      && binding.timelineRevision === request.revisions.timeline
    ));
}

function requestedBinding(request, minimumBinding) {
  return {
    level: minimumBinding,
    projectLibraryId: request.identities.projectLibraryId,
    ...(minimumBinding === "account/project-library" ? {} : {
      projectId: request.identities.projectId,
      projectRevision: request.revisions.project,
    }),
    ...(minimumBinding === "project+timeline" ? {
      timelineId: request.identities.timelineId,
      timelineRevision: request.revisions.timeline,
    } : {}),
  };
}

/** Owns live Mutation Policy scope selection and private payload digest binding. */
export function createSdkPreparedActionMutationBaseAuthority({resolveScope, registrations = {}} = {}) {
  if (typeof resolveScope !== "function") {
    throw new TypeError("Prepared mutation-base authority requires direct SDK scope resolution.");
  }
  return Object.freeze({
    async capture({request, authenticated, carrierBinding = {}}) {
      if (CUTAGENT_PREPARED_ACTION_ACTION_METADATA[request.actionId]?.operationClass !== "mutation") {
        throw new TypeError("Mutation-base authority cannot bind a read action.");
      }
      const registration = registrations[request.actionId];
      const minimumBinding = registration?.minimumBinding;
      if (!Object.hasOwn(RANK, minimumBinding)) throw new TypeError("Prepared mutation omitted its registered minimum binding.");
      const scope = await resolveScope({
        sdkSessionId: carrierBinding.sdkSessionId,
        accountFingerprint: authenticated.accountFingerprint,
        binding: requestedBinding(request, minimumBinding),
      });
      if (!scope || !exactScopeBinding(scope, request, minimumBinding)) {
        throw new TypeError("Prepared mutation requires one exact live Mutation Policy scope.");
      }
      const referencedPayloadDigests = typeof registration.resolveReferencedPayloadDigests === "function"
        ? await registration.resolveReferencedPayloadDigests({request: structuredClone(request)})
        : registration.referencedPayloadDigests;
      return sdkPreparedActionMutationBaseSchema.parse({
        contractVersion: 1,
        carrier: "sdk",
        minimumBinding,
        registryDigest: PRIVATE_IMPACT_REGISTRY_DIGEST,
        canonicalRequestDigest: mutationPolicyDigest(request),
        referencedPayloadDigests,
        requestId: request.requestId,
        operationId: request.operationId,
        executionId: request.executionId,
        scopeId: scope.scopeId,
        scopeRevision: scope.revision,
        projectLibraryId: request.identities.projectLibraryId,
        ...(minimumBinding === "account/project-library" ? {} : {
          projectId: request.identities.projectId,
          projectRevision: request.revisions.project,
        }),
        ...(minimumBinding === "project+timeline" ? {
          timelineId: request.identities.timelineId,
          timelineRevision: request.revisions.timeline,
        } : {}),
      });
    },
  });
}
