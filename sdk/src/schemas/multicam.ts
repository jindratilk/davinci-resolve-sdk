import { z } from "zod";
import {
  sdkMulticamAngleSchema,
  sdkMulticamCreateInputSchema,
  sdkMulticamCreateResultSchema,
  sdkMulticamFlattenInputSchema,
  sdkMulticamFlattenResultSchema,
  sdkMulticamSnapshotSchema,
  sdkMulticamSourceSchema,
  sdkMulticamSwitchInputSchema,
  sdkMulticamSwitchResultSchema,
} from "../generated/sdk-operations.js";
import type {
  MediaPoolItemId,
  MulticamAngleId,
  MulticamId,
  ProjectId,
  Revision,
  TimelineId,
} from "../value-types/identities.js";

/** Validated wire value for one multicam source snapshot. @beta */
export type MulticamSourceSnapshotValue = { mediaPoolItemId: MediaPoolItemId; name: string };
/** Validated wire value for one multicam angle snapshot. @beta */
export type MulticamAngleSnapshotValue = { id: MulticamAngleId; label: string; enabled: boolean | null; sources: MulticamSourceSnapshotValue[] };
/** Validated wire value for one multicam snapshot. @beta */
export type MulticamSnapshotValue = { id: MulticamId; projectId: ProjectId; revision: Revision; name: string; angles: MulticamAngleSnapshotValue[] };
/** Validated semantic multicam creation wire input. @beta */
export type MulticamCreateInputValue = {
  projectId: ProjectId;
  mediaPoolRevision: Revision;
  name: string;
  timelineName?: string;
  sources: { mediaPoolItemId: MediaPoolItemId; angleLabel: string }[];
  syncMode: "in" | "out" | "timecode" | "sound" | "marker";
  createTimeline: boolean;
};
/** Validated semantic multicam switching wire input. @beta */
export type MulticamSwitchInputValue = {
  projectId: ProjectId;
  timelineId: TimelineId;
  timelineRevision: Revision;
  multicamId: MulticamId;
  multicamRevision: Revision;
  switches: { atRecordFrame: number; angleId: MulticamAngleId; scope: "linked" | "video" | "audio" }[];
};
/** Validated semantic multicam flatten wire input. @beta */
export type MulticamFlattenInputValue = Omit<MulticamSwitchInputValue, "switches"> & {
  scope: "video" | "audio" | "both";
  gradePolicy: "copy_multicam" | "retain_angle";
};
/** Validated timeline identity returned by multicam mutations. @beta */
export type MulticamTimelineResultValue = { id: TimelineId; projectId: ProjectId; revision: Revision; name: string };
/** Validated semantic multicam creation wire result. @beta */
export type MulticamCreateResultValue = { actionId: "cutagent.action.multicam.create"; multicam: MulticamSnapshotValue; timeline: MulticamTimelineResultValue | null };
/** Validated semantic multicam switching wire result. @beta */
export type MulticamSwitchResultValue = { actionId: "cutagent.action.multicam.switch"; multicam: MulticamSnapshotValue; timeline: MulticamTimelineResultValue; changedSegments: number };
/** Validated semantic multicam flatten wire result. @beta */
export type MulticamFlattenResultValue = { actionId: "cutagent.action.multicam.flatten"; multicam: MulticamSnapshotValue; timeline: MulticamTimelineResultValue; changedSegments: number };

/** Public runtime validator for one multicam source snapshot. @beta */
export const MulticamSourceSnapshotSchema = sdkMulticamSourceSchema as unknown as z.ZodType<MulticamSourceSnapshotValue>;
/** Public runtime validator for one multicam angle snapshot. @beta */
export const MulticamAngleSnapshotSchema = sdkMulticamAngleSchema as unknown as z.ZodType<MulticamAngleSnapshotValue>;
/** Public runtime validator for one immutable multicam snapshot. @beta */
export const MulticamSnapshotSchema = sdkMulticamSnapshotSchema as unknown as z.ZodType<MulticamSnapshotValue>;
/** Public runtime validator for semantic multicam creation input. @beta */
export const MulticamCreateInputSchema = sdkMulticamCreateInputSchema as unknown as z.ZodType<MulticamCreateInputValue>;
/** Public runtime validator for semantic multicam switching input. @beta */
export const MulticamSwitchInputSchema = sdkMulticamSwitchInputSchema as unknown as z.ZodType<MulticamSwitchInputValue>;
/** Public runtime validator for semantic multicam flatten input. @beta */
export const MulticamFlattenInputSchema = sdkMulticamFlattenInputSchema as unknown as z.ZodType<MulticamFlattenInputValue>;
/** Public runtime validator for verified multicam creation results. @beta */
export const MulticamCreateResultSchema = sdkMulticamCreateResultSchema as unknown as z.ZodType<MulticamCreateResultValue>;
/** Public runtime validator for verified multicam switching results. @beta */
export const MulticamSwitchResultSchema = sdkMulticamSwitchResultSchema as unknown as z.ZodType<MulticamSwitchResultValue>;
/** Public runtime validator for verified multicam flatten results. @beta */
export const MulticamFlattenResultSchema = sdkMulticamFlattenResultSchema as unknown as z.ZodType<MulticamFlattenResultValue>;
