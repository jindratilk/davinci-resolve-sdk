import type { ActionInput } from "../actions.js";
import type { ColorTargetSnapshot } from "./object-model.js";
import { hydrateTimecode, lowerTimelineRecordPosition } from "../wire/time-adapter.js";
import type { ArtifactId, ProjectId, Revision, TimelineItemId } from "../value-types/identities.js";

/** First-class Color workflows above the complete typed action namespace. @beta */
export type ColorWorkflowActionId =
  | "cutagent.action.color.group.assign"
  | "cutagent.action.color.gallery.still.grab"
  | "cutagent.action.color.gallery.still.apply"
  | "cutagent.action.color.lut"
  | "cutagent.action.color.window.rectangle"
  | "cutagent.action.color.tracker.track_forward"
  | "cutagent.action.color.page.shot_match_apply";

/** One exact high-level Color workflow request accepted by `client.actions`. @beta */
export interface ColorWorkflowRequest<TAction extends ColorWorkflowActionId> {
  readonly actionId: TAction;
  readonly input: Readonly<ActionInput<TAction>>;
}

/** Stable project-scoped Color-group reference. @beta */
export interface ColorGroupReference { readonly projectId: ProjectId; readonly groupId: string; }
/** Stable project-scoped gallery-still reference. @beta */
export interface ColorStillReference { readonly projectId: ProjectId; readonly albumId: string; readonly stillId: string; }
/** Public artifact identity whose bytes remain in private CutAgent custody. @beta */
export interface ColorArtifactReference { readonly artifactId: ArtifactId; }
/** Revision-bound tracker reference returned by a typed Color inspection. @beta */
export interface ColorTrackerReference {
  readonly projectId: ProjectId;
  readonly timelineItemId: TimelineItemId;
  readonly colorRevision: Revision;
  readonly trackerId: string;
  readonly compIndex: number;
}
/** Bounded normalized rectangular Color-window geometry. @beta */
export interface ColorRectangleGeometry {
  readonly center: readonly [number, number];
  readonly width: number;
  readonly height: number;
  readonly softness?: number;
  readonly rotation?: number;
  readonly compIndex?: number;
}
/** Bounded shot-match controls using private artifact custody. @beta */
export interface ColorShotMatchOptions {
  readonly referenceFrame: number;
  readonly referenceArtifact: ColorArtifactReference;
  readonly targetArtifact: ColorArtifactReference;
  readonly anchor?: readonly [number, number];
  readonly radius?: number;
  readonly strength?: number;
}

/** One exact LUT application in a single or plural Color request. @beta */
export interface ColorLutApplication {
  readonly snapshot: ColorTargetSnapshot;
  readonly nodeIndex: number;
  readonly lutName: string;
}

/** Failure handling for a plural LUT application. @beta */
export interface ColorLutOptions {
  readonly failurePolicy?: "continue" | "stop";
}

/** Backward-compatible single-target LUT action request. @beta */
export interface ColorLutSingleRequest {
  readonly actionId: "cutagent.action.color.lut";
  readonly input: Readonly<Extract<ActionInput<"cutagent.action.color.lut">, { timelineItemId: unknown }>>;
}

/** One prepared plural LUT action request. @beta */
export interface ColorLutPluralRequest {
  readonly actionId: "cutagent.action.color.lut";
  readonly input: Readonly<{
    projectId: ProjectId;
    timelineId: string;
    revision: Revision;
    items: readonly Readonly<{
      timelineItemId: TimelineItemId;
      colorRevision: Revision;
      nodeStackLayerIndex: number;
      nodeIndex: number;
      lutName: string;
      clear: false;
    }>[];
    failurePolicy: "continue" | "stop";
  }>;
}

const ID = {
  group: /^group_[A-Za-z0-9][A-Za-z0-9._~-]*$/,
  album: /^album_[A-Za-z0-9][A-Za-z0-9._~-]*$/,
  still: /^still_[A-Za-z0-9][A-Za-z0-9._~-]*$/,
  artifact: /^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$/,
  tracker: /^color_entity_[A-Za-z0-9][A-Za-z0-9._~-]*$/,
} as const;

function freeze<T extends object>(value: T): Readonly<T> {
  if (!Array.isArray(value)) Object.setPrototypeOf(value, null);
  return Object.freeze(value);
}

function frame(snapshot: ColorTargetSnapshot): number {
  const lowered = lowerTimelineRecordPosition(snapshot.clip.recordRange.start, { frameRate: snapshot.frameRate });
  return lowered.value.kind === "frames" ? lowered.value.value : hydrateTimecode(lowered.value).toFrames().value;
}

function target(snapshot: ColorTargetSnapshot) {
  const timelineRevisionPrecondition = snapshot.timelineRevision;
  const colorRevisionPrecondition = snapshot.revision;
  return {
    projectId: snapshot.projectId,
    timelineId: snapshot.timelineId,
    timelineItemId: snapshot.clip.id,
    revision: timelineRevisionPrecondition,
    colorRevision: colorRevisionPrecondition,
  };
}

function nodeTarget(snapshot: ColorTargetSnapshot) {
  return { ...target(snapshot), nodeStackLayerIndex: snapshot.nodeStackLayerIndex };
}

function exactProject(snapshot: ColorTargetSnapshot, projectId: ProjectId): void {
  if (projectId !== String(snapshot.projectId)) throw new TypeError("Color workflow reference belongs to a different project snapshot.");
}

function exactId<T extends string>(value: T, pattern: RegExp, label: string): T {
  if (!pattern.test(value)) throw new TypeError(`${label} is not a valid opaque CutAgent identity.`);
  return value;
}

function bounded(value: number, minimum: number, maximum: number, label: string): number {
  if (!Number.isFinite(value) || value < minimum || value > maximum) throw new TypeError(`${label} is outside the bounded Color workflow contract.`);
  return value;
}

function request<A extends ColorWorkflowActionId>(actionId: A, input: ActionInput<A>): ColorWorkflowRequest<A> {
  return freeze({ actionId, input: freeze(input) }) as ColorWorkflowRequest<A>;
}

function applicationMode(value: number): 0 | 1 | 2 {
  if (value !== 0 && value !== 1 && value !== 2) throw new TypeError("Color application mode must be 0, 1, or 2.");
  return value;
}

function installedLutName(value: string): string {
  if (!value || value.length > 4096 || /[\0\r\n]/.test(value)
    || /^(?:\/|~\/|file:\/{2,3}|[A-Za-z]:[\\/]|\\\\)/i.test(value)
    || value.includes("\\")
    || value.split("/").some((segment) => segment === "." || segment === "..")) {
    throw new TypeError("LUT name must be an installed catalog name, not a local path.");
  }
  return value;
}

/** Build an exact current-clip Color-group assignment. @beta */
export function assignColorGroup(snapshot: ColorTargetSnapshot, group: ColorGroupReference) {
  exactProject(snapshot, group.projectId);
  return request("cutagent.action.color.group.assign", { ...target(snapshot), groupId: exactId(group.groupId, ID.group, "Color group") });
}

/** Build a still grab bound to the exact inspected clip and Color revision. @beta */
export function grabColorStill(snapshot: ColorTargetSnapshot) {
  return request("cutagent.action.color.gallery.still.grab", target(snapshot));
}

/** Build an exact gallery-still grade application. @beta */
export function applyColorStill(snapshot: ColorTargetSnapshot, still: ColorStillReference, mode: 0 | 1 | 2 = 0) {
  exactProject(snapshot, still.projectId);
  return request("cutagent.action.color.gallery.still.apply", { ...target(snapshot), albumId: exactId(still.albumId, ID.album, "Color album"), stillId: exactId(still.stillId, ID.still, "Color still"), mode: applicationMode(mode) });
}

/** Apply one installed public LUT name without exposing a local filesystem path. @beta */
export function applyColorLut(snapshot: ColorTargetSnapshot, nodeIndex: number, lutName: string): ColorLutSingleRequest;
/** Apply one or more exact LUT assignments in one prepared operation. @beta */
export function applyColorLut(applications: ColorLutApplication | readonly ColorLutApplication[], options?: ColorLutOptions): ColorLutPluralRequest;
export function applyColorLut(
  snapshotOrApplications: ColorTargetSnapshot | ColorLutApplication | readonly ColorLutApplication[],
  nodeIndexOrOptions?: number | ColorLutOptions,
  lutName?: string,
): ColorLutSingleRequest | ColorLutPluralRequest {
  if (typeof nodeIndexOrOptions === "number") {
    const snapshot = snapshotOrApplications as ColorTargetSnapshot;
    if (!snapshot.nodeGraph.nodes.some((node: { readonly index: number }) => node.index === nodeIndexOrOptions)) throw new TypeError("Color node reference is stale or outside the inspected graph.");
    return request("cutagent.action.color.lut", { ...nodeTarget(snapshot), nodeIndex: nodeIndexOrOptions, lutName: installedLutName(lutName ?? ""), clear: false }) as ColorLutSingleRequest;
  }

  const applications = Array.isArray(snapshotOrApplications)
    ? snapshotOrApplications
    : [snapshotOrApplications as ColorLutApplication];
  if (applications.length === 0 || applications.length > 128) throw new TypeError("LUT application requires between 1 and 128 exact targets.");
  const first = applications[0]!;
  const common = target(first.snapshot);
  const seen = new Set<string>();
  const items = applications.map(({ snapshot, nodeIndex, lutName: name }) => {
    if (snapshot.projectId !== common.projectId || snapshot.timelineId !== common.timelineId || snapshot.timelineRevision !== common.revision) {
      throw new TypeError("Plural LUT targets must belong to the same project, timeline, and inspected timeline revision.");
    }
    if (seen.has(String(snapshot.clip.id))) throw new TypeError("Plural LUT targets must be unique.");
    seen.add(String(snapshot.clip.id));
    if (!snapshot.nodeGraph.nodes.some((node: { readonly index: number }) => node.index === nodeIndex)) throw new TypeError("Color node reference is stale or outside the inspected graph.");
    return freeze({
      timelineItemId: snapshot.clip.id,
      colorRevision: snapshot.revision,
      nodeStackLayerIndex: snapshot.nodeStackLayerIndex,
      nodeIndex,
      lutName: installedLutName(name),
      clear: false as const,
    });
  });
  const options = nodeIndexOrOptions as ColorLutOptions | undefined;
  return request("cutagent.action.color.lut", {
    projectId: common.projectId,
    timelineId: common.timelineId,
    revision: common.revision,
    items,
    failurePolicy: options?.failurePolicy ?? "continue",
  }) as ColorLutPluralRequest;
}

/** Build an exact rectangular grading-window mutation. @beta */
export function createColorRectangle(snapshot: ColorTargetSnapshot, geometry: ColorRectangleGeometry) {
  const [x, y] = geometry.center;
  const compIndex = geometry.compIndex ?? 1;
  if (!Number.isInteger(compIndex) || compIndex < 1) throw new TypeError("Color composition index must be a positive integer.");
  return request("cutagent.action.color.window.rectangle", {
    ...target(snapshot),
    center: [bounded(x, 0, 1, "Window center X"), bounded(y, 0, 1, "Window center Y"), bounded(geometry.rotation ?? 0, -360, 360, "Window rotation")],
    width: bounded(geometry.width, 0, 1, "Window width"),
    height: bounded(geometry.height, 0, 1, "Window height"),
    softness: bounded(geometry.softness ?? 0, 0, 1, "Window softness"),
    compIndex,
  });
}

/** Build forward analysis for one revision-bound tracker reference. @beta */
export function trackColorForward(snapshot: ColorTargetSnapshot, tracker: ColorTrackerReference) {
  exactProject(snapshot, tracker.projectId);
  exactId(tracker.trackerId, ID.tracker, "Color tracker");
  if (tracker.timelineItemId !== String(snapshot.clip.id) || tracker.colorRevision !== String(snapshot.revision)) throw new TypeError("Color tracker reference is stale or belongs to another clip.");
  if (!Number.isSafeInteger(tracker.compIndex) || tracker.compIndex < 1) throw new TypeError("Color tracker reference is malformed.");
  return request("cutagent.action.color.tracker.track_forward", { ...target(snapshot), trackerName: tracker.trackerId, compIndex: tracker.compIndex });
}

/** Build a bounded exact-target shot-match operation with private artifact custody. @beta */
export function matchColorShot(snapshot: ColorTargetSnapshot, options: ColorShotMatchOptions) {
  const anchor = options.anchor ?? [0.5, 0.5];
  const radius = options.radius ?? 12;
  if (!Number.isSafeInteger(options.referenceFrame) || options.referenceFrame < 0 || !Number.isInteger(radius) || radius < 1 || radius > 200) throw new TypeError("Shot-match frame or radius is outside the bounded contract.");
  return request("cutagent.action.color.page.shot_match_apply", {
    ...target(snapshot), referenceFrame: options.referenceFrame, targetFrame: frame(snapshot),
    referenceArtifactId: exactId(options.referenceArtifact.artifactId, ID.artifact, "Reference-frame artifact"),
    targetArtifactId: exactId(options.targetArtifact.artifactId, ID.artifact, "Target-frame artifact"),
    anchorX: bounded(anchor[0], 0, 1, "Shot-match anchor X"), anchorY: bounded(anchor[1], 0, 1, "Shot-match anchor Y"),
    radius, strength: bounded(options.strength ?? 0.5, 0, 1, "Shot-match strength"),
  });
}
