import { connectDesktop } from "./connection/desktop-transport.js";
import { createCarrierClient } from "./core/client-core.js";
import {
  RuntimeSelectionSchema,
  type CutAgentClient,
  type CutAgentConnectOptions,
} from "./core/public-client-types.js";

export type {
  ConnectionControlOptions,
  ConnectionSnapshot,
  CutAgentClient,
  CutAgentConnectOptions,
  RuntimeSelection,
} from "./core/public-client-types.js";

/** Runtime selection policy for `CutAgent.connect()`. @beta */
export { RuntimeSelectionSchema } from "./core/public-client-types.js";

async function createClient(options: CutAgentConnectOptions): Promise<CutAgentClient> {
  RuntimeSelectionSchema.parse(options.runtime ?? "auto");
  return createCarrierClient(
    (control) => connectDesktop(control),
    {
      ...(options.timeoutMs !== undefined
        ? { timeoutMs: options.timeoutMs, retainedTimeoutMs: options.timeoutMs }
        : {}),
      ...(options.signal !== undefined ? { signal: options.signal } : {}),
    },
  );
}

/** Canonical non-constructible namespace for creating explicit CutAgent SDK clients. @beta */
export const CutAgent: Readonly<{
  /** Connect to a compatible desktop-managed CutAgent runtime without reserving paid usage. */
  connect(options?: CutAgentConnectOptions): Promise<CutAgentClient>;
}> = Object.freeze({
  connect(options: CutAgentConnectOptions = {}): Promise<CutAgentClient> {
    return createClient(options);
  },
});
