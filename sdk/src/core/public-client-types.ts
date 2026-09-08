import { z } from "zod";
import type { Projects } from "../domain/object-model.js";
import type { Operations } from "../protocol/operations.js";
import type { Actions } from "../actions.js";
import type { CompatibilityDescriptor } from "../protocol/compatibility.js";
import type { Voice } from "../domain/voice.js";
import type { ConnectionId, SdkSessionId } from "../value-types/identities.js";
import type { Workflows } from "./workflows.js";
import type { Artifacts } from "../domain/artifacts.js";

/** Runtime selection policy for `CutAgent.connect()`. @beta */
export const RuntimeSelectionSchema = z.enum(["auto", "standalone_local"]);
/** Runtime selection policy for `CutAgent.connect()`. @beta */
export type RuntimeSelection = "auto" | "standalone_local";

/** Options for a bounded SDK control request. @beta */
export interface ConnectionControlOptions {
  /** Maximum time for this control request. */
  timeoutMs?: number;
  /** Abort only the local request; it does not claim server-side cancellation. */
  signal?: AbortSignal;
}

/** Options for creating a CutAgent SDK client. @beta */
export interface CutAgentConnectOptions extends ConnectionControlOptions {
  /** Select the desktop-managed runtime carrier. */
  runtime?: RuntimeSelection;
}

/** Sanitized immutable view of one SDK connection. @beta */
export interface ConnectionSnapshot {
  /** Opaque identity for this client connection. */
  readonly connectionId: ConnectionId;
  /** Opaque identity for the associated runtime session. */
  readonly sessionId: SdkSessionId;
  /** Sanitized live compatibility and runtime identity. */
  readonly descriptor: CompatibilityDescriptor;
  /** ISO timestamp at which the runtime issued the session. */
  readonly issuedAt: string;
  /** Absolute ISO expiry for the runtime session. */
  readonly expiresAt: string;
  /** Current idle-expiry timestamp as issued at connection time. */
  readonly idleExpiresAt: string;
}

/** Public client contract for one isolated CutAgent runtime session. @beta */
export interface CutAgentClient {
  /** Current sanitized connection metadata. Credentials and local endpoints are never exposed. */
  readonly connection: ConnectionSnapshot;
  /** Whether this client currently has no usable runtime session. */
  readonly closed: boolean;
  /** Live read-only project entry point for this explicit client session. */
  readonly projects: Projects;
  /** Durable operation control and reattachment independent of object-model generations. */
  readonly operations: Operations;
  /** Typed secondary namespace for reviewed, result-backed low-level semantic actions. */
  readonly actions: Actions;
  /** Publish Fusion setting input and open path-free managed artifacts. */
  readonly artifacts: Artifacts;
  /** Hosted generated-voice operations; timeline placement lives on `Timeline.voiceovers`. */
  readonly voice: Voice;
  /** Serial checkpoint-backed composition over durable operations. Never implies atomic rollback. */
  readonly workflows: Workflows;
  /** Close the runtime session. Repeated calls are idempotent and never retry transport requests. */
  close(options?: ConnectionControlOptions): Promise<void>;
  /** Establish a fresh runtime session for this client after close or carrier loss. */
  reconnect(options?: ConnectionControlOptions): Promise<ConnectionSnapshot>;
}
