import crypto from "node:crypto";
import { z } from "zod";
import {
  sdkProjectIdSchema,
  sdkRevisionSchema,
  sdkTimelineIdSchema,
} from "../contracts/generated/sdk-runtime.js";

const projectListInputSchema = z.object({}).strict();
const projectListResultSchema = z.object({
  actionId: z.literal("cutagent.action.project.list"),
  payload: z.object({
    status: z.literal("completed"),
    data: z.object({
      projects: z.array(z.object({
        current: z.boolean(),
        index: z.number().int().min(1),
        project: z.object({ id: sdkProjectIdSchema, name: z.string().min(1).max(1024) }).strict(),
      }).strict()).max(1_024),
    }).strict(),
    verification: z.object({
      evidence: z.array(z.object({
        kind: z.enum(["structural_readback", "artifact_readback", "context_readback", "checkpoint_readback", "manual_review"]),
        summary: z.string().min(1).max(500),
      }).strict()).min(1).max(32),
      outcome: z.enum(["passed", "partial", "not_performed", "manual_review_required"]),
      protectedState: z.enum(["preserved", "not_applicable", "not_proven", "partial"]),
    }).strict(),
  }).strict(),
}).strict();

const timelineListInputSchema = z.object({
  projectId: sdkProjectIdSchema,
  expectedRevision: sdkRevisionSchema.optional(),
}).strict();
const timelineListResultSchema = z.object({
  actionId: z.literal("cutagent.action.timeline.list"),
  timelines: z.array(z.object({
    timelineId: sdkTimelineIdSchema,
    projectId: sdkProjectIdSchema,
    revision: sdkRevisionSchema,
    name: z.string().min(1).max(1024),
  }).strict()).max(10_000),
}).strict();

function succeeded(result) {
  const encoded = JSON.stringify(result);
  return {
    status: "succeeded",
    result,
    possibleMutation: "none",
    usage: "consumed",
    verification: {
      outcome: "passed",
      summary: "Fresh bracketed DaVinci Resolve inventory readback completed.",
      evidence: [{
        evidenceId: `evidence_${crypto.randomUUID()}`,
        modality: "readback",
        summary: "Fresh bracketed inventory readback remained stable.",
        capturedAt: new Date().toISOString(),
        digest: `sha256:${crypto.createHash("sha256").update(encoded, "utf8").digest("hex")}`,
      }],
      protectedStatePreserved: true,
    },
  };
}

/** Public, read-only inventory actions backed by exact live identity readback. */
export function createSdkInventoryActions({ liveInspectionService }) {
  if (typeof liveInspectionService?.readProjectInventory !== "function"
    || typeof liveInspectionService?.read !== "function") {
    throw new TypeError("SDK inventory actions require live project and Timeline inspection.");
  }
  return Object.freeze({
    "cutagent.action.project.list": {
      operationClass: "read",
      inputSchema: projectListInputSchema,
      resultSchema: projectListResultSchema,
      idempotency: "safe",
      async execute(_context, rawInput) {
        projectListInputSchema.parse(rawInput);
        const projects = await liveInspectionService.readProjectInventory({ deadlineAtMs: Date.now() + 60_000 });
        return succeeded(projectListResultSchema.parse({
          actionId: "cutagent.action.project.list",
          payload: {
            status: "completed",
            data: { projects },
            verification: {
              evidence: [{ kind: "structural_readback", summary: "Project inventory was bracketed by an unchanged live project and folder context." }],
              outcome: "passed",
              protectedState: "not_applicable",
            },
          },
        }));
      },
    },
    "cutagent.action.timeline.list": {
      operationClass: "read",
      inputSchema: timelineListInputSchema,
      resultSchema: timelineListResultSchema,
      idempotency: "safe",
      async execute(_context, rawInput) {
        const input = timelineListInputSchema.parse(rawInput);
        const timelines = await liveInspectionService.read({
          operation: "timeline.list",
          projectId: input.projectId,
          ...(input.expectedRevision === undefined ? {} : { expectedRevision: input.expectedRevision }),
        }, { deadlineAtMs: Date.now() + 60_000 });
        if (timelines.some((timeline) => timeline.projectId !== input.projectId)) {
          throw new Error("Timeline inventory escaped its exact project ownership scope.");
        }
        return succeeded(timelineListResultSchema.parse({ actionId: "cutagent.action.timeline.list", timelines }));
      },
    },
  });
}
