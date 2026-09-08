import { createHash } from "node:crypto";
import { open, unlink } from "node:fs/promises";
import path from "node:path";
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
          if (typeof destinationPath !== "string" || !path.isAbsolute(destinationPath)) {
            throw new TypeError("Artifact destinationPath must be absolute.");
          }
          let handle;
          let created = false;
          try {
            handle = await open(destinationPath, "wx+", 0o600);
            created = true;
            const hash = createHash("sha256");
            let offset = 0;
            while (offset < receipt.byteCount) {
              const bytes = await readChunk(offset, Math.min(1024 * 1024, receipt.byteCount - offset), options);
              if (bytes.length < 1 || offset + bytes.length > receipt.byteCount) throw invalidResponse("Managed artifact content ended inconsistently.");
              let written = 0;
              while (written < bytes.length) {
                const result = await handle.write(bytes, written, bytes.length - written, offset + written);
                if (!Number.isInteger(result.bytesWritten) || result.bytesWritten < 1) {
                  throw invalidResponse("Managed artifact destination stopped before a verified chunk was written.");
                }
                written += result.bytesWritten;
              }
              hash.update(bytes);
              offset += bytes.length;
            }
            await handle.sync();
            if ((await handle.stat()).size !== receipt.byteCount || `sha256:${hash.digest("hex")}` !== receipt.canonicalSha256) {
              throw invalidResponse("Copied managed artifact did not match its verified receipt.");
            }
          } catch (error) {
            await handle?.close().catch(() => {});
            handle = undefined;
            if (created) await unlink(destinationPath).catch(() => {});
            throw error;
          } finally {
            await handle?.close();
          }
        },
      };
      Object.setPrototypeOf(artifact, null);
      return Object.freeze(artifact);
    },
  });
}
