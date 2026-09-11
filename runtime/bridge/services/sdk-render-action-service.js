import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { execFile, spawn } from "node:child_process";
import { promisify } from "node:util";
import {
  sdkRenderExportResultSchema,
  sdkRenderExportInputSchema,
} from "../contracts/generated/sdk-operations.js";
import { resolveAttachmentFfprobePath } from "../../local/native-tools.mjs";
import {
  assertCanonicalPrivateDirectory,
  ensureCanonicalPrivateDirectory,
} from "./private-storage.js";
import { createSdkRenderQueueStartAction } from "./sdk-render-queue-start-action.js";

const execFileAsync = promisify(execFile);
const ACTION_ID = "cutagent.action.render.export";
const FORMAT = Object.freeze({ quicktime: "QuickTime", mp4: "MP4", mxf: "MXF OP1A", wave: "Wave", aiff: "AIFF" });
const CODEC = Object.freeze({ h264: "H.264", h265: "H.265", prores: "Apple ProRes", dnxhr: "DNxHR", av1: "AV1", linear_pcm: "Linear PCM", aac: "AAC", flac: "FLAC" });
const EXTENSION = Object.freeze({ quicktime: "mov", mp4: "mp4", mxf: "mxf", wave: "wav", aiff: "aiff" });
const COMPLETE = new Set(["complete", "completed", "success", "succeeded"]);
const FAILED = new Set(["failed", "error", "cancelled", "canceled", "aborted"]);
const ACTIVE = new Set(["rendering", "in_progress"]);
const QUEUED = new Set(["queued", "pending"]);
const CODEC_FAMILY = Object.freeze({
  h264: new Set(["h264", "avc", "avc1"]),
  h265: new Set(["hevc", "h265", "hev1", "hvc1"]),
  prores: new Set(["prores"]),
  dnxhr: new Set(["dnxhd", "dnxhr"]),
  av1: new Set(["av1"]),
  linear_pcm: new Set(["pcm"]),
  aac: new Set(["aac"]),
  flac: new Set(["flac"]),
});
const sleep = (milliseconds) => new Promise((resolve) => {
  const timer = setTimeout(resolve, milliseconds);
  timer.unref?.();
});

function envelope(output) {
  const value = typeof output === "string" ? JSON.parse(output) : output;
  if (!value || value.ok !== true) {
    const error = new Error("CutAgent CLI render action failed.");
    error.code = value?.error?.code || "OPERATION_FAILED";
    error.privateCause = value?.error;
    throw error;
  }
  return value;
}

function evidence(modality, summary, digest = undefined, artifactId = undefined) {
  return {
    evidenceId: `evidence_${crypto.randomUUID()}`,
    modality,
    summary,
    capturedAt: new Date().toISOString(),
    ...(digest ? { digest } : {}),
    ...(artifactId ? { artifactId } : {}),
  };
}

const PUBLIC_FAILURE_MESSAGE = Object.freeze({
  CAPABILITY_UNAVAILABLE: "The requested render format and codec are unavailable in the current environment.",
  STALE_REVISION: "The exact render timeline changed before the authorized step could run.",
  VERIFICATION_FAILED: "The completed render artifact did not pass independent verification.",
  RECOVERY_FAILED: "The interrupted render could not be reconciled to one exact completed native job.",
  CANCELLED: "The render operation stopped after a confirmed cancellation request.",
  OPERATION_FAILED: "The render operation could not complete safely.",
});

function exactFailureCode(error) {
  const raw = error?.privateCause?.code ?? error?.code;
  return typeof raw === "string" && /^[A-Z][A-Z0-9_]{0,99}$/.test(raw) ? raw : "OPERATION_FAILED";
}

function operationFailure(code, context, possibleMutation, usage, readbackRequired = possibleMutation !== "none", causeCode = undefined) {
  const kind = code === "CAPABILITY_UNAVAILABLE" ? "capability_unavailable"
    : code === "STALE_REVISION" ? "stale_revision"
    : code === "VERIFICATION_FAILED" ? "verification_failed"
      : code === "RECOVERY_FAILED" ? "recovery_failed" : "operation_failed";
  return {
    kind,
    code,
    message: PUBLIC_FAILURE_MESSAGE[code] ?? PUBLIC_FAILURE_MESSAGE.OPERATION_FAILED,
    retrySafe: false,
    possibleMutation,
    usage,
    recovery: readbackRequired ? ["inspect_state", "manual_recovery"] : ["inspect_state"],
    recoveryGuidance: [readbackRequired
      ? "Inspect the original render operation and managed output before creating replacement work."
      : "Refresh the exact project and timeline revision before creating a new render operation."],
    readbackRequired,
    requestId: context.requestId,
    operationId: context.operationId,
    executionId: context.executionId,
    ...(causeCode ? { cause: { code: causeCode, message: "The native render step returned this exact failure code." } } : {}),
    ...(code === "RECOVERY_FAILED" ? {
      recoveryOutcome: { status: "failed", summary: "The interrupted render could not be reconciled automatically.", manualRecoveryRequired: true },
    } : {}),
  };
}

function failureTruth(state) {
  if (state.renderCompleted) return { possibleMutation: "confirmed", usage: "consumed", readbackRequired: true };
  if (state.renderStarted || state.jobEnqueued || state.startAttempted || state.enqueueAttempted) return { possibleMutation: "partial", usage: "consumed", readbackRequired: true };
  if (state.settingsApplied || state.modeApplied || state.settingsAttempted || state.modeAttempted) return { possibleMutation: "partial", usage: "consumed", readbackRequired: true };
  return { possibleMutation: "none", usage: "not_reserved", readbackRequired: false };
}

class RenderStopRequested extends Error {
  constructor() {
    super("render stop requested");
    this.name = "RenderStopRequested";
  }
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function codecMatches(requested, actual) {
  if (typeof actual !== "string" || !actual) return false;
  const normalized = actual.trim().toLowerCase().replaceAll("-", "_");
  return [...CODEC_FAMILY[requested]].some((family) => normalized === family || normalized.startsWith(`${family}_`));
}

function stableTimelineState(snapshot) {
  return {
    project: snapshot.project,
    timeline: snapshot.timeline,
    frameRate: snapshot.frameRate,
    start: snapshot.start,
    markers: snapshot.markers?.map(({ snapshotRevision: _revision, ...marker }) => marker) ?? [],
    tracks: snapshot.tracks.map((track) => ({
      type: track.type,
      index: track.index,
      name: track.name,
      enabled: track.enabled,
      locked: track.locked,
      clips: track.clips.map(({ snapshotId: _snapshotId, snapshotTrackId: _trackId, snapshotRevision: _revision, ...clip }) => clip),
    })),
  };
}

function canonicalDigest(value) {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
}

function jobRows(response) {
  return Array.isArray(response?.data) ? response.data : [];
}

function rawJobId(row) {
  return String(row?.job_id ?? row?.JobId ?? "");
}

function rawJobTarget(row) {
  return path.resolve(String(row?.target ?? row?.TargetDir ?? ""));
}

function rawJobFilename(row) {
  return String(row?.filename ?? row?.OutputFileName ?? row?.OutputFilename ?? "");
}

function exactJob(rows, directory, filename) {
  const matches = rows.filter((row) => rawJobTarget(row) === directory && rawJobFilename(row) === filename && rawJobId(row));
  if (matches.length === 0) return null;
  if (matches.length > 1) {
    const error = new Error("More than one native render job matches the managed output identity.");
    error.code = "AMBIGUOUS_RENDER_JOB";
    throw error;
  }
  return matches[0];
}

function normalizedJobStatus(data) {
  const row = Array.isArray(data?.jobs) ? data.jobs[0] : null;
  if (!row) return { status: "unknown", progress: null, row: null };
  const status = String(row?.cutagent_job_status?.normalized_status ?? row?.RenderJobStatus ?? row?.JobStatus ?? row?.status ?? "unknown").trim().toLowerCase();
  const rawProgress = Number(row?.cutagent_job_status?.progress ?? row?.CompletionPercentage ?? row?.progress);
  return { status, progress: Number.isFinite(rawProgress) && rawProgress >= 0 && rawProgress <= 100 ? rawProgress : null, row };
}

async function sha256File(_filePath, descriptor) {
  const hash = crypto.createHash("sha256");
  await new Promise((resolve, reject) => {
    const stream = fs.createReadStream(null, { fd: descriptor, autoClose: false, start: 0 });
    stream.on("data", (chunk) => hash.update(chunk));
    stream.once("error", reject);
    stream.once("end", resolve);
  });
  return `sha256:${hash.digest("hex")}`;
}

function rate(value) {
  if (typeof value !== "string" || !value) return null;
  const [numerator, denominator = "1"] = value.split("/", 2).map(Number);
  const result = numerator / denominator;
  return Number.isFinite(result) && result > 0 ? result : null;
}

async function probeFile(_filePath, descriptor) {
  if (!Number.isInteger(descriptor) || descriptor < 0) throw new Error("Render artifact verification requires a bound file descriptor.");
  const input = process.platform === "win32" ? "pipe:3" : "/dev/fd/3";
  const stdout = await new Promise((resolve, reject) => {
    const child = spawn(resolveAttachmentFfprobePath(), [
      "-v", "error",
      "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,channels,duration",
      "-of", "json",
      input,
    ], { stdio: ["ignore", "pipe", "pipe", descriptor], windowsHide: true });
    const output = [];
    let outputBytes = 0;
    let settled = false;
    const finish = (error, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error); else resolve(value);
    };
    const timer = setTimeout(() => {
      child.kill();
      finish(new Error("FFprobe timed out while verifying the bound render artifact."));
    }, 30_000);
    timer.unref?.();
    child.once("error", () => finish(new Error("FFprobe could not inspect the bound render artifact.")));
    child.stdout.on("data", (chunk) => {
      outputBytes += chunk.length;
      if (outputBytes > 512 * 1024) {
        child.kill();
        finish(new Error("FFprobe output exceeded the verification limit."));
        return;
      }
      output.push(chunk);
    });
    child.stderr.resume();
    child.once("close", (code) => finish(
      code === 0 ? null : new Error("FFprobe rejected the bound render artifact."),
      Buffer.concat(output).toString("utf8"),
    ));
  });
  return parseProbeMediaOutput(JSON.parse(stdout));
}

export function parseProbeMediaOutput(parsed) {
  const streams = Array.isArray(parsed?.streams) ? parsed.streams : [];
  const video = streams.find((stream) => stream?.codec_type === "video") ?? null;
  const audio = streams.find((stream) => stream?.codec_type === "audio") ?? null;
  const primaryDuration = Number(video?.duration ?? audio?.duration);
  const containerDuration = Number(parsed?.format?.duration);
  const duration = Number.isFinite(primaryDuration) && primaryDuration > 0
    ? primaryDuration
    : containerDuration;
  return {
    durationSeconds: Number.isFinite(duration) && duration > 0 ? duration : null,
    width: Number.isInteger(video?.width) && video.width > 0 ? video.width : null,
    height: Number.isInteger(video?.height) && video.height > 0 ? video.height : null,
    frameRate: rate(video?.avg_frame_rate || video?.r_frame_rate),
    videoCodec: typeof video?.codec_name === "string" && video.codec_name ? video.codec_name : null,
    audioCodec: typeof audio?.codec_name === "string" && audio.codec_name ? audio.codec_name : null,
    audioChannels: Number.isInteger(audio?.channels) && audio.channels > 0 ? audio.channels : null,
  };
}

async function verifyArtifact({ directory, expectedFilename, input, before, after, probeMedia, hashArtifact, assertDirectory }) {
  assertDirectory();
  const candidate = path.join(directory, expectedFilename);
  if (path.dirname(candidate) !== directory || path.basename(candidate) !== expectedFilename) throw new Error("Render output identity escaped its managed destination.");
  const initialPathStat = fs.lstatSync(candidate);
  if (!initialPathStat.isFile() || initialPathStat.isSymbolicLink() || initialPathStat.size < 1) throw new Error("Render output is not a non-empty regular file.");
  const noFollow = Number.isInteger(fs.constants.O_NOFOLLOW) ? fs.constants.O_NOFOLLOW : 0;
  const descriptor = fs.openSync(candidate, fs.constants.O_RDONLY | noFollow);
  const openedStat = fs.fstatSync(descriptor);
  const identity = Object.freeze({ dev: openedStat.dev, ino: openedStat.ino, size: openedStat.size });
  const assertArtifactIdentity = () => {
    assertDirectory();
    const pathStat = fs.lstatSync(candidate);
    const descriptorStat = fs.fstatSync(descriptor);
    if (
      !pathStat.isFile()
      || pathStat.isSymbolicLink()
      || !descriptorStat.isFile()
      || pathStat.dev !== identity.dev
      || pathStat.ino !== identity.ino
      || pathStat.size !== identity.size
      || descriptorStat.dev !== identity.dev
      || descriptorStat.ino !== identity.ino
      || descriptorStat.size !== identity.size
    ) throw new Error("Render output file identity changed during verification.");
  };
  if (
    !openedStat.isFile()
    || initialPathStat.dev !== identity.dev
    || initialPathStat.ino !== identity.ino
    || initialPathStat.size !== identity.size
  ) {
    fs.closeSync(descriptor);
    throw new Error("Render output file changed while it was being bound for verification.");
  }
  try {
    assertArtifactIdentity();
    const extension = path.extname(expectedFilename).slice(1).toLowerCase();
    if (extension !== EXTENSION[input.settings.format]) throw new Error("Render output extension does not match the requested format.");
    const sha256 = await hashArtifact(candidate, descriptor);
    assertArtifactIdentity();
    const media = await probeMedia(candidate, descriptor);
    assertArtifactIdentity();
    if (input.settings.exportVideo && (!media.videoCodec || !media.width || !media.height)) throw new Error("FFprobe did not confirm the requested video stream.");
    if (!input.settings.exportVideo && media.videoCodec) throw new Error("FFprobe found an unexpected video stream.");
    if (input.settings.exportAudio && !media.audioCodec) throw new Error("FFprobe did not confirm the requested audio stream.");
    if (!input.settings.exportAudio && media.audioCodec) throw new Error("FFprobe found an unexpected audio stream.");
    const deliveredCodec = input.settings.exportVideo ? media.videoCodec : media.audioCodec;
    if (!codecMatches(input.settings.codec, deliveredCodec)) throw new Error("FFprobe codec metadata does not match the requested codec family.");
    if (!media.durationSeconds) throw new Error("FFprobe did not confirm a positive output duration.");
    if (input.range.kind === "custom") {
      const timelineRate = Number(before.frameRate?.numerator) / Number(before.frameRate?.denominator);
      const expectedDuration = (input.range.endExclusiveFrame - input.range.startFrame) / timelineRate;
      const tolerance = Math.max(0.1, 2 / timelineRate);
      if (!Number.isFinite(expectedDuration) || !Number.isFinite(timelineRate) || timelineRate <= 0
        || Math.abs(media.durationSeconds - expectedDuration) > tolerance) {
        throw new Error("Rendered duration does not match the requested custom range.");
      }
    }
    if (input.settings.width && (media.width !== input.settings.width || media.height !== input.settings.height)) throw new Error("Rendered dimensions do not match the requested settings.");
    if (input.settings.exportVideo && !media.frameRate) throw new Error("FFprobe did not confirm the rendered frame rate.");
    if (input.settings.frameRate && (!media.frameRate || Math.abs(media.frameRate - input.settings.frameRate) > 0.01)) throw new Error("Rendered frame rate does not match the requested settings.");
    const artifactId = `artifact_${crypto.randomUUID()}`;
    const protectedStatePreserved = canonicalDigest(stableTimelineState(before)) === canonicalDigest(stableTimelineState(after));
    const artifact = {
      artifactId,
      basename: expectedFilename,
      extension,
      sizeBytes: identity.size,
      sha256,
      media,
    };
    const report = {
      outcome: protectedStatePreserved ? "passed" : "failed",
      summary: protectedStatePreserved
        ? "The exact managed render output passed filesystem, hash, FFprobe, and protected timeline verification."
        : "The render output passed file validation but protected timeline state changed.",
      evidence: [
        evidence("readback", "Read back the terminal native render job and exact active timeline."),
        evidence("structural", "Compared protected timeline structure before and after rendering.", canonicalDigest(stableTimelineState(after))),
        evidence("file", "Verified exact output identity, regular-file state, non-empty size, and SHA-256 digest.", sha256, artifactId),
        evidence("rendered", "FFprobe validated the completed output media streams and technical metadata.", sha256, artifactId),
      ],
      protectedStatePreserved,
    };
    assertArtifactIdentity();
    return { artifact, report };
  } finally {
    fs.closeSync(descriptor);
  }
}

function settingsMatch(snapshot, input) {
  const requested = input.settings;
  return snapshot.projectId === input.projectId
    && snapshot.format?.kind === "known" && snapshot.format.value === requested.format
    && snapshot.codec?.kind === "known" && snapshot.codec.value === requested.codec
    && (!requested.width || (snapshot.resolution?.width === requested.width && snapshot.resolution?.height === requested.height))
    && (!requested.frameRate || (snapshot.frameRate !== null && Math.abs(snapshot.frameRate - requested.frameRate) <= 0.01))
    && snapshot.exportVideo === requested.exportVideo
    && snapshot.exportAudio === requested.exportAudio
    && snapshot.customName === input.output.baseName;
}

function rangeMatches(snapshot, input, timelineStart = 0) {
  if (input.range.kind === "full_timeline") return snapshot.range?.kind === "full_timeline";
  return snapshot.range?.kind === "custom"
    && snapshot.range.markInFrame === timelineStart + input.range.startFrame
    && snapshot.range.markOutFrame === timelineStart + input.range.endExclusiveFrame - 1;
}

function renderSettingsExplicitlyUnavailable(snapshot) {
  return snapshot?.support?.availability === "unavailable"
    && snapshot.support.reason === "api_unavailable";
}

function recordFrame(value) {
  if (Number.isSafeInteger(value)) return value;
  const frame = value?.value?.value;
  return Number.isSafeInteger(frame) ? frame : null;
}

function renderRangeFromSnapshot(snapshot, input) {
  const timelineStart = recordFrame(snapshot?.start);
  if (timelineStart === null) return null;
  if (input.range.kind === "custom") {
    return {
      markInFrame: timelineStart + input.range.startFrame,
      markOutFrame: timelineStart + input.range.endExclusiveFrame - 1,
    };
  }
  const ends = (snapshot?.tracks ?? []).flatMap((track) => (
    (track?.clips ?? []).map((clip) => recordFrame(clip?.recordRange?.endExclusive))
  )).filter(Number.isSafeInteger);
  if (ends.length === 0) return null;
  return { markInFrame: timelineStart, markOutFrame: Math.max(...ends) - 1 };
}

function discoverySupports(discovery, input) {
  const format = discovery?.formats?.find((entry) => (
    entry?.format?.kind === "known" && entry.format.value === input.settings.format
  ));
  if (!format || format.codecSupport?.availability !== "supported") return false;
  const codec = format.codecs?.find((entry) => (
    entry?.codec?.kind === "known"
    && entry.codec.value === input.settings.codec
  ));
  if (!codec) return false;
  if (!input.settings.width) return true;
  return codec.resolutionSupport?.availability === "supported"
    && codec.resolutions?.some((resolution) => (
      resolution?.width === input.settings.width && resolution?.height === input.settings.height
    )) === true;
}

function modeIsSingle(response) {
  return Number(response?.data?.mode) === 1 || response?.data?.description === "single";
}

export function createSdkRenderActionDefinitions({
  toolExecutionService,
  liveInspectionService,
  managedRenderRoot,
  artifactService,
  probeMedia = probeFile,
  hashArtifact = sha256File,
  wait = sleep,
  beforeNativeDispatch = null,
}) {
  if (typeof toolExecutionService?.executeCutAgentCliCommand !== "function"
    || typeof liveInspectionService?.readWithMutationGuard !== "function"
    || typeof liveInspectionService?.read !== "function"
    || typeof liveInspectionService?.resolveRenderJobBinding !== "function"
    || typeof liveInspectionService?.resolveRenderJobSelections !== "function"
    || typeof artifactService?.register !== "function"
    || typeof managedRenderRoot !== "string" || !path.isAbsolute(managedRenderRoot)
    || typeof probeMedia !== "function" || typeof hashArtifact !== "function" || typeof wait !== "function"
    || (beforeNativeDispatch !== null && typeof beforeNativeDispatch !== "function")) {
    throw new TypeError("SDK render actions require CutAgent CLI, live inspection, and an absolute managed render root.");
  }
  const root = fs.realpathSync(ensureCanonicalPrivateDirectory(managedRenderRoot, {
    label: "Managed render root",
  }));
  const rootStat = fs.lstatSync(root);
  const rootIdentity = Object.freeze({ dev: rootStat.dev, ino: rootStat.ino });
  const states = new Map();
  let ownershipTail = Promise.resolve();
  const acquireOwnership = async () => {
    const previous = ownershipTail;
    const release = deferred();
    ownershipTail = release.promise;
    await previous;
    return () => release.resolve();
  };
  const run = async (args, options = {}) => envelope(await toolExecutionService.executeCutAgentCliCommand({ args, expect_json: true }, options));
  const coordinates = (context, input) => {
    const directory = path.join(root, context.operationId);
    const extension = EXTENSION[input.settings.format];
    return { directory, filename: `${input.output.baseName}.${extension}` };
  };
  const assertRenderRoot = () => {
    const currentRoot = fs.realpathSync(assertCanonicalPrivateDirectory(root, { label: "Managed render root" }));
    const stat = fs.lstatSync(currentRoot);
    if (currentRoot !== root || stat.dev !== rootIdentity.dev || stat.ino !== rootIdentity.ino) {
      throw new Error("Managed render root identity changed.");
    }
  };
  const bindOperationDirectory = (state) => {
    assertRenderRoot();
    const canonical = fs.realpathSync(ensureCanonicalPrivateDirectory(state.directory, {
      label: "Managed render operation directory",
    }));
    const relative = path.relative(root, canonical);
    if (canonical !== state.directory || !relative || relative.startsWith("..") || path.isAbsolute(relative)) {
      throw new Error("Managed render operation directory escaped its canonical root.");
    }
    const stat = fs.lstatSync(canonical);
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error("Managed render operation directory is not canonical.");
    state.directoryIdentity = { dev: stat.dev, ino: stat.ino };
  };
  const assertOperationDirectory = (state) => {
    assertRenderRoot();
    const canonical = fs.realpathSync(assertCanonicalPrivateDirectory(state.directory, {
      label: "Managed render operation directory",
    }));
    const stat = fs.lstatSync(canonical);
    const relative = path.relative(root, canonical);
    if (
      canonical !== state.directory
      || !relative
      || relative.startsWith("..")
      || path.isAbsolute(relative)
      || !stat.isDirectory()
      || stat.isSymbolicLink()
      || !state.directoryIdentity
      || stat.dev !== state.directoryIdentity.dev
      || stat.ino !== state.directoryIdentity.ino
    ) {
      throw new Error("Managed render operation directory identity changed.");
    }
  };
  const currentSnapshot = async (input) => {
    const inspected = await liveInspectionService.readWithMutationGuard({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, { deadlineAtMs: Date.now() + 60_000 });
    if (inspected.value.revision !== input.timelineRevision) {
      const error = new Error("The exact timeline revision changed before rendering.");
      error.code = "STALE_REVISION";
      throw error;
    }
    if (typeof inspected.mutationGuard !== "string" || !/^sha256:[a-f0-9]{64}$/.test(inspected.mutationGuard)) {
      const error = new Error("The exact render mutation guard was unavailable.");
      error.code = "STALE_REVISION";
      throw error;
    }
    return inspected;
  };
  const assertRunning = (state) => {
    if (state.stopRequested) throw new RenderStopRequested();
  };
  const withPolicy = async (args, state, { allowStopped = false, onAuthorized = null } = {}) => {
    if (!allowStopped) assertRunning(state);
    assertOperationDirectory(state);
    const response = await run(args, {
      mutationGuard: state.mutationGuard,
      onAuthorization() {
        if (!state.executionStartedReported) {
          state.context.reportExecutionStarted?.();
          state.executionStartedReported = true;
        }
        onAuthorized?.();
      },
    });
    assertOperationDirectory(state);
    if (!allowStopped) assertRunning(state);
    return response;
  };
  const findExactJob = async (directory, filename) => exactJob(jobRows(await run(["render", "jobs"])), directory, filename);
  const awaitTerminal = async (state) => {
    let maximumProgress = 0;
    for (;;) {
      assertRunning(state);
      if (state.context.isCancellationRequested?.()) {
        await wait(250);
        continue;
      }
      let response;
      try {
        response = await run(["render", "status", "--job", state.jobId]);
      } catch (error) {
        if (state.stopRequested) throw new RenderStopRequested();
        const cancellationProof = state.cancellationInProgress ? state.cancellationProof : null;
        if (cancellationProof) {
          const confirmed = await cancellationProof.promise;
          if (confirmed || state.stopRequested) throw new RenderStopRequested();
        }
        throw error;
      }
      if (state.cancellationInProgress && state.cancellationProof) {
        const confirmed = await state.cancellationProof.promise;
        if (confirmed || state.stopRequested) throw new RenderStopRequested();
      }
      const status = normalizedJobStatus(response.data);
      assertRunning(state);
      if (status.progress !== null) maximumProgress = Math.max(maximumProgress, status.progress);
      state.context.reportProgress?.({
        phase: "rendering",
        overallFraction: 0.08 + (maximumProgress / 100) * 0.9,
        phaseFraction: maximumProgress / 100,
      });
      if (COMPLETE.has(status.status)) return status;
      if (FAILED.has(status.status)) {
        const error = new Error(`Native render job reached terminal status: ${status.status}.`);
        error.code = "OPERATION_FAILED";
        error.status = status;
        throw error;
      }
      await wait(500);
    }
  };
  const reconcileAmbiguousStart = async (state) => {
    try {
      const job = await liveInspectionService.resolveRenderJobBinding({
        projectId: state.input.projectId,
        nativeJobId: state.jobId,
      }, { deadlineAtMs: Date.now() + 30_000 });
      if (job.statusSupport?.availability !== "supported" || job.status?.kind !== "known") return null;
      if (job.status.value === "completed") return "completed";
      if (job.status.value === "rendering") return "rendering";
      return null;
    } catch {
      return null;
    }
  };
  const successfulResult = async (state) => {
    assertRunning(state);
    assertOperationDirectory(state);
    const inspectedAfter = await currentSnapshot(state.input);
    assertRunning(state);
    assertOperationDirectory(state);
    if (inspectedAfter.mutationGuard !== state.mutationGuard) throw new Error("The exact timeline mutation guard changed during rendering.");
    const after = inspectedAfter.value;
    const completedJob = await liveInspectionService.resolveRenderJobBinding({
      projectId: state.input.projectId,
      nativeJobId: state.jobId,
    }, { deadlineAtMs: Date.now() + 30_000 });
    if (completedJob.statusSupport?.availability !== "supported"
      || completedJob.status?.kind !== "known"
      || completedJob.status.value !== "completed") {
      throw Object.assign(new Error("The exact native render job did not have independently readable completed status."), { code: "VERIFICATION_FAILED" });
    }
    assertOperationDirectory(state);
    const verified = await verifyArtifact({
      directory: state.directory,
      expectedFilename: state.filename,
      input: state.input,
      before: state.before,
      after,
      probeMedia,
      hashArtifact,
      assertDirectory: () => assertOperationDirectory(state),
    });
    assertOperationDirectory(state);
    if (!verified.report.protectedStatePreserved) throw Object.assign(new Error("Protected timeline state changed during rendering."), { verification: verified.report });
    assertOperationDirectory(state);
    const registered = artifactService.register({
      artifactId: verified.artifact.artifactId,
      operationId: state.context.operationId,
      accountFingerprint: state.context.accountFingerprint,
      filePath: path.join(state.directory, state.filename),
      sizeBytes: verified.artifact.sizeBytes,
      sha256: verified.artifact.sha256,
    });
    return {
      status: "succeeded",
      possibleMutation: "confirmed",
      usage: "consumed",
      verification: verified.report,
      result: sdkRenderExportResultSchema.parse({
        projectId: state.input.projectId,
        timelineId: state.input.timelineId,
        timelineRevision: after.revision,
        job: { id: completedJob.id, queueRevision: completedJob.queueRevision },
        artifact: { ...verified.artifact, ...registered },
      }),
    };
  };
  const cancellationOutcome = (state) => {
    const { possibleMutation, usage } = failureTruth(state);
    return {
      status: "cancelled",
      possibleMutation,
      usage,
      cancellation: {
        state: "confirmed",
        requestedAt: state.cancelRequestedAt,
        confirmedAt: new Date().toISOString(),
      },
      failure: {
        kind: "cancelled",
        code: "CANCELLED",
        message: PUBLIC_FAILURE_MESSAGE.CANCELLED,
        retrySafe: false,
        possibleMutation,
        usage,
        recovery: possibleMutation === "none" ? ["continue"] : ["inspect_state"],
        recoveryGuidance: [possibleMutation === "none"
          ? "No native render mutation was started."
          : "Inspect the current render settings and exact owned job before replacement work."],
        readbackRequired: possibleMutation !== "none",
        requestId: state.context.requestId,
        operationId: state.context.operationId,
        executionId: state.context.executionId,
      },
    };
  };
  const cleanupQueuedCancellation = async (state) => {
    try {
      const row = await findExactJob(state.directory, state.filename);
      if (!row) return true;
      const jobId = rawJobId(row);
      if (state.jobId && jobId !== state.jobId) return false;
      const status = normalizedJobStatus({ jobs: [row] });
      if (!QUEUED.has(status.status)) return false;
      state.jobId = jobId;
      await withPolicy(["render", "delete", "--job", jobId], state, { allowStopped: true });
      return !(await findExactJob(state.directory, state.filename));
    } catch {
      return false;
    }
  };
  const execute = async (context, rawInput) => {
    const input = sdkRenderExportInputSchema.parse(rawInput);
    const { directory, filename } = coordinates(context, input);
    const settled = deferred();
    const state = {
      context, input, directory, filename, phase: "waiting_for_ownership", jobId: null,
      before: null, mutationGuard: null,
      stopRequested: false, cancelRequestedAt: null, settled: settled.promise, directoryIdentity: null,
      cancellationInProgress: false, cancellationProof: null,
      cancellationConfirmed: false,
      executionStartedReported: false,
      modeAttempted: false, modeApplied: false, settingsAttempted: false, settingsApplied: false,
      enqueueAttempted: false, jobEnqueued: false, startAttempted: false, renderStarted: false, renderCompleted: false,
    };
    states.set(context.operationId, state);
    let releaseOwnership = null;
    try {
      releaseOwnership = await acquireOwnership();
      assertRunning(state);
      state.phase = "preparing";
      try {
        const inspected = await currentSnapshot(input);
        assertRunning(state);
        state.before = inspected.value;
        state.mutationGuard = inspected.mutationGuard;
        const discovery = await liveInspectionService.read({ operation: "render.discovery", projectId: input.projectId }, { deadlineAtMs: Date.now() + 30_000 });
        if (!discoverySupports(discovery, input)) {
          const unavailable = new Error("The requested render format and codec pair is unavailable.");
          unavailable.code = "CAPABILITY_UNAVAILABLE";
          throw unavailable;
        }
      } catch (error) {
        if (error instanceof RenderStopRequested) throw error;
        const exactCode = exactFailureCode(error);
        const code = ["STALE_REVISION", "CAPABILITY_UNAVAILABLE"].includes(exactCode) ? exactCode : "OPERATION_FAILED";
        return { status: "failed", possibleMutation: "none", usage: "not_reserved", failure: operationFailure(code, context, "none", "not_reserved", false, exactCode) };
      }
      assertRunning(state);
      if (beforeNativeDispatch !== null) {
        context.reportExecutionStarted?.();
        state.executionStartedReported = true;
        await beforeNativeDispatch(Object.freeze({
          actionId: ACTION_ID,
          requestId: context.requestId,
          operationId: context.operationId,
          executionId: context.executionId,
        }));
      }
      bindOperationDirectory(state);
      state.context.reportProgress({ phase: "configuring", overallFraction: 0.02, phaseFraction: 0.1 });
      state.phase = "configuring";
      const settings = input.settings;
      await withPolicy(["render", "mode", "set", "single"], state, { onAuthorized() { state.modeAttempted = true; } });
      state.modeApplied = true;
      if (!modeIsSingle(await run(["render", "mode", "get"]))) {
        const error = new Error("Native render mode readback did not confirm single-clip mode.");
        error.code = "VERIFICATION_FAILED";
        throw error;
      }
      await withPolicy([
        "render", "settings-set", "--target", directory, "--name", input.output.baseName,
        "--format", FORMAT[settings.format], "--codec", CODEC[settings.codec],
        settings.exportVideo ? "--video" : "--no-video", settings.exportAudio ? "--audio" : "--no-audio",
        ...(input.range.kind === "full_timeline" ? ["--full-timeline"] : []),
        ...(settings.width ? ["--width", String(settings.width), "--height", String(settings.height)] : []),
        ...(settings.frameRate ? ["--fps", String(settings.frameRate)] : []),
      ], state, { onAuthorized() { state.settingsAttempted = true; } });
      state.settingsApplied = true;
      state.phase = "configured";
      const configuredInspection = await currentSnapshot(input);
      assertRunning(state);
      if (configuredInspection.mutationGuard !== state.mutationGuard) throw Object.assign(new Error("Render timeline drifted after configuration."), { code: "STALE_REVISION" });
      const settingsReadback = await liveInspectionService.read({ operation: "render.settings", projectId: input.projectId }, { deadlineAtMs: Date.now() + 30_000 });
      assertRunning(state);
      const settingsReadable = !renderSettingsExplicitlyUnavailable(settingsReadback);
      const timelineStart = recordFrame(state.before.start);
      if (settingsReadable && (!settingsMatch(settingsReadback, input)
        || (input.range.kind === "full_timeline" && !rangeMatches(settingsReadback, input, timelineStart ?? 0)))) {
        const error = new Error("Native render settings did not confirm the requested configuration.");
        error.code = "VERIFICATION_FAILED";
        throw error;
      }
      state.context.reportProgress({ phase: "enqueueing", overallFraction: 0.05, phaseFraction: 0.2 });
      state.phase = "enqueueing";
      const added = await withPolicy([
        "render", "add",
        ...(input.range.kind === "custom" ? ["--in", `${input.range.startFrame}f`, "--out", `${input.range.endExclusiveFrame - 1}f`] : []),
      ], state, { onAuthorized() { state.enqueueAttempted = true; } });
      const jobId = String(added?.data?.job_id ?? added?.data?.target?.job_id ?? "");
      if (!jobId) throw new Error("CutAgent CLI did not return the newly enqueued render job identity.");
      state.jobId = jobId;
      state.jobEnqueued = true;
      state.phase = "enqueued";
      const row = await findExactJob(directory, filename);
      assertRunning(state);
      if (!row || rawJobId(row) !== jobId) throw new Error("The newly enqueued job did not match the exact managed output identity.");
      const enqueuedSettings = await liveInspectionService.read({ operation: "render.settings", projectId: input.projectId }, { deadlineAtMs: Date.now() + 30_000 });
      const enqueuedSettingsReadable = !renderSettingsExplicitlyUnavailable(enqueuedSettings);
      const expectedRange = renderRangeFromSnapshot(state.before, input);
      const queuedConfigurationMatches = await liveInspectionService.verifyRenderJobConfiguration({
        projectId: input.projectId,
        nativeJobId: jobId,
        expected: {
          targetDir: directory,
          outputFilename: filename,
          format: settings.format,
          codec: settings.codec,
          exportVideo: settings.exportVideo,
          exportAudio: settings.exportAudio,
          width: settings.width ?? null,
          height: settings.height ?? null,
          frameRate: settings.frameRate ?? null,
          ...(expectedRange ?? {}),
        },
      }, { deadlineAtMs: Date.now() + 30_000 });
      if ((!enqueuedSettingsReadable && !queuedConfigurationMatches)
        || (enqueuedSettingsReadable && (!settingsMatch(enqueuedSettings, input) || !rangeMatches(enqueuedSettings, input, timelineStart ?? 0)))
        || !modeIsSingle(await run(["render", "mode", "get"]))) {
        const error = new Error("The queued render did not preserve single-clip full-timeline settings.");
        error.code = "VERIFICATION_FAILED";
        throw error;
      }
      const enqueuedInspection = await currentSnapshot(input);
      assertRunning(state);
      if (enqueuedInspection.mutationGuard !== state.mutationGuard) throw Object.assign(new Error("Render timeline drifted after enqueue."), { code: "STALE_REVISION" });
      state.context.reportProgress({ phase: "starting", overallFraction: 0.08, phaseFraction: 0.5 });
      state.phase = "starting";
      let recoveredStart = null;
      try {
        await withPolicy(["render", "start", "--jobs", jobId, "--no-wait"], state, { onAuthorized() { state.startAttempted = true; } });
      } catch (startError) {
        recoveredStart = await reconcileAmbiguousStart(state);
        if (recoveredStart === null) throw startError;
      }
      state.renderStarted = true;
      state.phase = "rendering";
      if (recoveredStart !== "completed") await awaitTerminal(state);
      state.renderCompleted = true;
      state.phase = "verifying";
      state.context.reportProgress({ phase: "verifying", overallFraction: 0.99, phaseFraction: 0.5 });
      return await successfulResult(state);
    } catch (caught) {
      if (caught?.p211EvaluatorDeadlineFault === true) throw caught;
      let error = caught;
      if (!(error instanceof RenderStopRequested) && state.cancellationInProgress && state.cancellationProof) {
        const confirmed = await state.cancellationProof.promise;
        if (confirmed || state.stopRequested) error = new RenderStopRequested();
      }
      if (error instanceof RenderStopRequested) {
        const mayHaveQueuedJob = state.jobId || ["enqueueing", "enqueued"].includes(state.phase);
        if (mayHaveQueuedJob && !await cleanupQueuedCancellation(state)) {
          return {
            status: "partially_applied", possibleMutation: "partial", usage: "consumed",
            failure: operationFailure("OPERATION_FAILED", context, "partial", "consumed"),
            recovery: { state: "manual_required", summary: "The exact owned render job could not be safely removed.", evidence: [], manualRecoveryRequired: true },
          };
        }
        state.cancellationConfirmed = true;
        return cancellationOutcome(state);
      }
      const truth = failureTruth(state);
      const { possibleMutation, usage } = truth;
      const exactCode = exactFailureCode(error);
      if (state.renderCompleted || error?.verification) {
        const report = error?.verification ?? {
          outcome: "failed",
          summary: "The terminal render output could not be independently validated.",
          evidence: [evidence("file", "Managed output validation failed after native rendering.")],
          protectedStatePreserved: null,
        };
        return { status: "verification_failed", possibleMutation: "confirmed", usage, failure: operationFailure("VERIFICATION_FAILED", context, "confirmed", usage, true, exactCode), verification: report };
      }
      const code = possibleMutation === "none" && ["STALE_REVISION", "CAPABILITY_UNAVAILABLE"].includes(exactCode) ? exactCode : "OPERATION_FAILED";
      if (possibleMutation === "none") return { status: "failed", possibleMutation, usage, failure: operationFailure(code, context, possibleMutation, usage, false, exactCode) };
      return {
        status: "partially_applied",
        possibleMutation,
        usage,
        failure: operationFailure("OPERATION_FAILED", context, possibleMutation, usage, truth.readbackRequired, exactCode),
        recovery: { state: "manual_required", summary: "Render settings, queue state, or partial output may remain and require inspection.", evidence: [], manualRecoveryRequired: true },
      };
    } finally {
      releaseOwnership?.();
      settled.resolve();
      states.delete(context.operationId);
    }
  };
  const cancel = async (context, rawInput) => {
    const input = sdkRenderExportInputSchema.parse(rawInput);
    const state = states.get(context.operationId);
    if (!state) return { confirmed: false, reason: "The active render executor could not be correlated for cancellation." };
    const phaseAtRequest = state.phase;
    if (["waiting_for_ownership", "preparing", "configuring", "configured", "enqueueing", "enqueued"].includes(phaseAtRequest)) {
      state.cancelRequestedAt = new Date().toISOString();
      state.stopRequested = true;
      await state.settled;
      if (!state.cancellationConfirmed) {
        return { confirmed: false, reason: "The exact queued native render job could not be removed safely." };
      }
      const { possibleMutation, usage } = failureTruth(state);
      return {
        confirmed: true,
        possibleMutation,
        usage,
        readbackRequired: possibleMutation !== "none",
      };
    }
    if (phaseAtRequest === "starting") {
      return { confirmed: false, reason: "Cancellation is unavailable while the exact native start command is settling." };
    }
    if (phaseAtRequest === "verifying") {
      return { confirmed: false, reason: "The native render already completed and independent verification is in progress." };
    }
    if (phaseAtRequest !== "rendering" || !state.jobId) {
      return { confirmed: false, reason: "The exact owned native render job is not cancellable in its current phase." };
    }
    const cancellationProof = deferred();
    state.cancellationInProgress = true;
    state.cancellationProof = cancellationProof;
    const resolveCancellationProof = (confirmed) => {
      cancellationProof.resolve(confirmed);
      state.cancellationInProgress = false;
    };
    try {
      await withPolicy([
        "render", "cancel", "--job", state.jobId, "--delete-queued", "--require-exclusive-job",
      ], state);
      if (await findExactJob(state.directory, state.filename)) {
        resolveCancellationProof(false);
        return { confirmed: false, reason: "The exact owned native render job remains after the cancellation attempt." };
      }
      state.cancelRequestedAt = new Date().toISOString();
      state.stopRequested = true;
      resolveCancellationProof(true);
      await state.settled;
      return { confirmed: true, possibleMutation: "partial", usage: "consumed", readbackRequired: true };
    } catch {
      resolveCancellationProof(false);
      return { confirmed: false, reason: "Exact sole-job native cancellation could not be proven safely." };
    }
  };
  const reconcile = async (context, rawInput) => {
    const input = sdkRenderExportInputSchema.parse(rawInput);
    const { directory, filename } = coordinates(context, input);
    const state = {
      context: { ...context, reportProgress() {}, isCancellationRequested() { return false; } },
      input, directory, filename, phase: "reconciling", jobId: null,
      before: null, mutationGuard: null, stopRequested: false, directoryIdentity: null,
    };
    let releaseOwnership = null;
    try {
      releaseOwnership = await acquireOwnership();
      bindOperationDirectory(state);
      const inspected = await currentSnapshot(input);
      state.before = inspected.value;
      state.mutationGuard = inspected.mutationGuard;
      const row = await findExactJob(directory, filename);
      if (!row) throw new Error("The interrupted render has no exact correlated native job.");
      state.jobId = rawJobId(row);
      const status = normalizedJobStatus({ jobs: [row] });
      if (FAILED.has(status.status)) throw new Error("The exact native render job ended unsuccessfully.");
      if (!COMPLETE.has(status.status) && !ACTIVE.has(status.status)) throw new Error("The exact native render job is not active or complete.");
      if (ACTIVE.has(status.status)) await awaitTerminal(state);
      return await successfulResult(state);
    } catch {
      return {
        status: "recovery_failed",
        possibleMutation: "possible",
        usage: context.snapshot?.usage ?? "unknown",
        failure: operationFailure("RECOVERY_FAILED", context, "possible", context.snapshot?.usage ?? "unknown"),
        recovery: { state: "failed", summary: "The interrupted render could not be reconciled to an exact verified output.", evidence: [], manualRecoveryRequired: true },
      };
    } finally { releaseOwnership?.(); }
  };
  return Object.freeze({
    [ACTION_ID]: {
      inputSchema: sdkRenderExportInputSchema,
      resultSchema: sdkRenderExportResultSchema,
      idempotency: "required",
      execute,
      cancel,
      reconcile,
    },
    "cutagent.action.render.start": createSdkRenderQueueStartAction({
      liveInspectionService,
      run,
      acquireOwnership,
      wait,
    }),
  });
}
