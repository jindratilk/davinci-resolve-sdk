import {sdkPreparedActionMutationBaseSchema} from "../contracts/generated/sdk-prepared-action.js";
import {CUTAGENT_PREPARED_ACTION_ACTION_METADATA} from "../contracts/sdk-prepared-action-metadata.generated.js";
import {preparedActionRequestDigest, PRIVATE_IMPACT_REGISTRY_DIGEST} from "./sdk-prepared-action-request-integrity.js";

const RANK = Object.freeze({"account/project-library": 1, project: 2, "project+timeline": 3});

/** Owns exact target-depth selection and private payload digest binding. */
export function createSdkPreparedActionMutationBaseAuthority({registrations = {}} = {}) {
  return Object.freeze({
    async capture({request}) {
      if (CUTAGENT_PREPARED_ACTION_ACTION_METADATA[request.actionId]?.operationClass !== "mutation") {
        throw new TypeError("Mutation-base authority cannot bind a read action.");
      }
      const registration = registrations[request.actionId];
      const minimumBinding = registration?.minimumBinding;
      if (!Object.hasOwn(RANK, minimumBinding)) throw new TypeError("Prepared mutation omitted its registered minimum binding.");
      const referencedPayloadDigests = typeof registration.resolveReferencedPayloadDigests === "function"
        ? await registration.resolveReferencedPayloadDigests({request: structuredClone(request)})
        : registration.referencedPayloadDigests;
      return sdkPreparedActionMutationBaseSchema.parse({
        contractVersion: 1,
        carrier: "sdk",
        minimumBinding,
        registryDigest: PRIVATE_IMPACT_REGISTRY_DIGEST,
        canonicalRequestDigest: preparedActionRequestDigest(request),
        referencedPayloadDigests,
        requestId: request.requestId,
        operationId: request.operationId,
        executionId: request.executionId,
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
