import { copyVerifiedArtifact } from "./artifact-copy.js";
import type { CarrierReadRequest, CarrierReadSuccess } from "../core/carrier-session.js";
import type { ConnectionControlOptions } from "../core/public-client-types.js";
import { sdkArtifactIdSchema } from "../generated/sdk-identities.js";
import { CutAgentSdkError, PUBLIC_ERROR_KIND_BY_CODE } from "../protocol/errors.js";
import { ArtifactIdSchema, RequestIdSchema, type ArtifactId } from "../value-types/identities.js";

/** Path-free receipt returned by a managed-artifact action. @beta */
export interface ManagedArtifactReceipt {
  readonly artifactId: ArtifactId;
  readonly mediaType: string;
  readonly byteCount: number;
  readonly sha256: string;
}

/** Open managed artifact content bound to one exact receipt. @beta */
export interface ManagedArtifact extends ManagedArtifactReceipt {
  /** Read one bounded content chunk without exposing the runtime's private path. */
  readContent(options: Readonly<{ offset: number; length: number }> & ConnectionControlOptions): Promise<Uint8Array>;
  /** Copy and verify the complete artifact into a new caller-owned local file without overwriting. */
  copyTo(destinationPath: string, options?: ConnectionControlOptions): Promise<void>;
}

/** Managed content access for artifacts returned by typed semantic actions. @beta */
export interface Artifacts {
  /** Publish one bounded UTF-8 Fusion `.setting` document into private managed custody. */
  publishFusionSetting(source: string | Uint8Array, options?: ConnectionControlOptions): Promise<ManagedArtifactReceipt>;
  /** Bind a sanitized action receipt to verified managed content reads. */
  open(receipt: ManagedArtifactReceipt): ManagedArtifact;
}

interface ArtifactRuntime {
  readonly generation: number;
  readAtGeneration(generation: number, request: CarrierReadRequest, options?: ConnectionControlOptions): Promise<CarrierReadSuccess>;
}

function invalidResponse(message: string, requestId?: string): CutAgentSdkError {
  return new CutAgentSdkError({
    kind: PUBLIC_ERROR_KIND_BY_CODE.INVALID_RESPONSE,
    code: "INVALID_RESPONSE",
    message,
    retrySafe: false,
    possibleMutation: "none",
    usage: "not_reserved",
    recovery: ["contact_support"],
    recoveryGuidance: [message],
    readbackRequired: false,
    ...(requestId ? { requestId: RequestIdSchema.parse(requestId) } : {}),
  });
}

function parseReceipt(value: ManagedArtifactReceipt): ManagedArtifactReceipt & { canonicalSha256: `sha256:${string}` } {
  if (value === null || typeof value !== "object") throw new TypeError("Managed artifact receipt must be an object.");
  const artifactId = ArtifactIdSchema.parse(value.artifactId);
  if (typeof value.mediaType !== "string" || !/^[^\s/]+\/[^\s/]+$/.test(value.mediaType)) {
    throw new TypeError("Managed artifact mediaType must be a MIME type.");
  }
  if (!Number.isSafeInteger(value.byteCount) || value.byteCount < 1) {
    throw new TypeError("Managed artifact byteCount must be a positive safe integer.");
  }
  const rawDigest = typeof value.sha256 === "string" ? value.sha256 : "";
  const canonicalSha256 = (/^[a-f0-9]{64}$/.test(rawDigest) ? `sha256:${rawDigest}` : rawDigest) as `sha256:${string}`;
  if (!/^sha256:[a-f0-9]{64}$/.test(canonicalSha256)) throw new TypeError("Managed artifact sha256 is invalid.");
  return { artifactId, mediaType: value.mediaType, byteCount: value.byteCount, sha256: rawDigest, canonicalSha256 };
}

/** Create the client-scoped managed artifact namespace. @internal */
export function createArtifacts(runtime: ArtifactRuntime): Artifacts {
  return Object.freeze({
    async publishFusionSetting(source: string | Uint8Array, options: ConnectionControlOptions = {}): Promise<ManagedArtifactReceipt> {
      const bytes = typeof source === "string" ? Buffer.from(source, "utf8") : source instanceof Uint8Array ? Buffer.from(source) : null;
      if (!bytes || bytes.length < 1 || bytes.length > 4 * 1024 * 1024) {
        throw new TypeError("Fusion setting source must contain 1 through 4194304 UTF-8 bytes.");
      }
      const response = await runtime.readAtGeneration(runtime.generation, {
        operation: "artifact.fusion_setting.publish", setting: {bytesBase64: bytes.toString("base64")},
      }, options);
      if (response.operation !== "artifact.fusion_setting.publish") throw invalidResponse("CutAgent runtime returned the wrong Fusion setting artifact result.", response.requestId);
      return Object.freeze(parseReceipt(response.data));
    },
    open(receiptValue: ManagedArtifactReceipt): ManagedArtifact {
      const generation = runtime.generation;
      const receipt = parseReceipt(receiptValue);
      const wireArtifactId = sdkArtifactIdSchema.parse(receipt.artifactId);
      const readChunk = async (offset: number, length: number, options: ConnectionControlOptions): Promise<Uint8Array> => {
        if (!Number.isSafeInteger(offset) || offset < 0) throw new RangeError("Artifact offset must be a non-negative safe integer.");
        if (!Number.isInteger(length) || length < 1 || length > 1024 * 1024) throw new RangeError("Artifact length must be from 1 through 1048576 bytes.");
        const response = await runtime.readAtGeneration(generation, {
          operation: "artifact.content", artifactId: wireArtifactId, offset, length,
        }, options);
        if (response.operation !== "artifact.content") throw invalidResponse("CutAgent runtime returned the wrong artifact content result.", response.requestId);
        const data = response.data;
        if (data.artifactId !== wireArtifactId || data.offset !== offset || data.totalSize !== receipt.byteCount
          || data.sha256 !== receipt.canonicalSha256) {
          throw invalidResponse("CutAgent runtime returned content for a different managed artifact.", response.requestId);
        }
        return Uint8Array.from(Buffer.from(data.bytesBase64, "base64"));
      };
      const artifact: ManagedArtifact = {
        artifactId: receipt.artifactId,
        mediaType: receipt.mediaType,
        byteCount: receipt.byteCount,
        sha256: receipt.sha256,
        readContent({ offset, length, ...options }) { return readChunk(offset, length, options); },
        async copyTo(destinationPath, options = {}) {
          await copyVerifiedArtifact({
            destinationPath, sizeBytes: receipt.byteCount, sha256: receipt.canonicalSha256,
            readChunk: (offset, length) => readChunk(offset, length, options), invalidResponse,
          });
        },
      };
      Object.setPrototypeOf(artifact, null);
      return Object.freeze(artifact);
    },
  });
}
