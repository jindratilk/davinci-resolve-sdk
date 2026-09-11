import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { z } from "zod";
import {
  sdkAutoCaptionInputSchema,
  sdkDesignedCaptionInputSchema,
  sdkSubtitleExportInputSchema,
  sdkSubtitleInsertInputSchema,
  sdkSubtitleListInputSchema,
  sdkTranscriptCreateInputSchema,
} from "../contracts/generated/sdk-operations.js";
import { assertAuthenticatedSdkRequestCurrent, captureAuthenticatedSdkRequest } from "./sdk-authenticated-request.js";
import { issueCutAgentCliBrokerEnvironment } from "./cutagent-cli-broker-grant.js";

const id = (prefix) => `${prefix}${crypto.randomUUID()}`;
const verificationResult = z.object({ revision: z.string().regex(/^revision_/), evidenceCount: z.number().int().min(1) }).strict();
const listResult = z.object({ revision: z.string().regex(/^revision_/), items: z.array(z.object({
  id: z.string().regex(/^snapshot_timeline_item_/), trackId: z.string().regex(/^snapshot_track_/), trackIndex: z.number().int().min(1),
  text: z.string(), recordRange: z.object({ domain: z.literal("timeline_record_range"), unit: z.literal("frames"), start: z.number().int(), endExclusive: z.number().int() }).strict(),
}).strict()), timelineId: z.string().regex(/^timeline_/), frameRate: z.object({ numerator: z.number().int().positive(), denominator: z.number().int().positive(), nominalTimebase: z.number().int().positive() }).strict() }).strict();
const definitions = {
  "cutagent.action.timeline.subtitle.list": {
    inputSchema: sdkSubtitleListInputSchema, resultSchema: listResult, idempotency: "optional",
  },
  "cutagent.action.timeline.subtitle.insert": {
    inputSchema: sdkSubtitleInsertInputSchema,
    resultSchema: z.object({ matchedEntries: z.number().int().min(1), createdTrack: z.boolean(), verification: verificationResult }).strict(), idempotency: "required",
  },
  "cutagent.action.timeline.subtitle.export": {
    inputSchema: sdkSubtitleExportInputSchema,
    resultSchema: z.object({ format: z.enum(["srt", "vtt", "ttml"]), content: z.string(), exportedEntries: z.number().int().min(0), sha256: z.string().regex(/^[a-f0-9]{64}$/) }).strict(), idempotency: "required",
  },
  "cutagent.action.timeline.auto_caption": {
    inputSchema: sdkAutoCaptionInputSchema,
    resultSchema: z.object({ createdItems: z.number().int().min(1), verification: verificationResult }).strict(), idempotency: "required",
  },
  "cutagent.action.text.insert_captions": {
    inputSchema: sdkDesignedCaptionInputSchema,
    resultSchema: z.object({ insertedItems: z.number().int().min(1), trackIndex: z.number().int().min(1), verification: verificationResult }).strict(), idempotency: "required",
  },
  "cutagent.action.transcript.create": {
    inputSchema: sdkTranscriptCreateInputSchema,
    resultSchema: z.object({ provider: z.string().min(1), model: z.string().min(1), languageCode: z.string().nullable(), text: z.string(), words: z.array(z.object({ text: z.string(), startSeconds: z.number().min(0), endSeconds: z.number().min(0), speaker: z.string().nullable() }).strict()).max(200_000), durationSeconds: z.number().min(0).nullable(), deliveryAcknowledged: z.literal(true), deliveryRecovered: z.boolean() }).strict(), idempotency: "required",
  },
};

function envelope(output) {
  const value = typeof output === "string" ? JSON.parse(output) : output;
  if (!value || value.ok !== true) {
    const error = new Error(value?.error?.message || "CutAgent CLI action failed.");
    error.code = value?.error?.code || "OPERATION_FAILED";
    error.details = value?.error?.details;
    throw error;
  }
  return value;
}

function evidence(summary, modality = "readback", digest = undefined) {
  return { evidenceId: id("evidence_"), modality, summary, capturedAt: new Date().toISOString(), ...(digest ? { digest } : {}) };
}

function verification(summary, entries, protectedStatePreserved = null) {
  return { outcome: "passed", summary, evidence: entries, protectedStatePreserved };
}

function digest(prefix, value) {
  return `${prefix}${crypto.createHash("sha256").update(JSON.stringify(value)).digest("base64url")}`;
}

function waitForReconciliation(delayMs) {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, delayMs);
    timer.unref?.();
  });
}

function subtitleTimestamp(frame, fps, separator) {
  const totalMilliseconds = Math.max(0, Math.round((Number(frame) / fps) * 1000));
  const hours = Math.floor(totalMilliseconds / 3_600_000);
  const minutes = Math.floor((totalMilliseconds % 3_600_000) / 60_000);
  const seconds = Math.floor((totalMilliseconds % 60_000) / 1000);
  const milliseconds = totalMilliseconds % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}${separator}${String(milliseconds).padStart(3, "0")}`;
}

function serializeSubtitles(rows, format, fps, timelineStartFrame) {
  if (format === "ttml") {
    const xml = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&apos;");
    const cues = rows.map((row) => `      <p begin="${subtitleTimestamp(Number(row.start_frame) - timelineStartFrame, fps, ".")}" end="${subtitleTimestamp(Number(row.end_frame) - timelineStartFrame, fps, ".")}">${xml(row.text)}</p>`);
    return `<?xml version="1.0" encoding="UTF-8"?>\n<tt xmlns="http://www.w3.org/ns/ttml">\n  <body>\n    <div>\n${cues.join("\n")}${cues.length ? "\n" : ""}    </div>\n  </body>\n</tt>\n`;
  }
  const cues = rows.map((row, index) => {
    const timing = `${subtitleTimestamp(Number(row.start_frame) - timelineStartFrame, fps, format === "srt" ? "," : ".")} --> ${subtitleTimestamp(Number(row.end_frame) - timelineStartFrame, fps, format === "srt" ? "," : ".")}`;
    return `${format === "srt" ? `${index + 1}\n` : ""}${timing}\n${String(row.text ?? "")}`;
  });
  return `${format === "vtt" ? "WEBVTT\n\n" : ""}${cues.join("\n\n")}${cues.length ? "\n" : ""}`;
}

function assertTrackExists(snapshot, type, index) {
  const track = snapshot.tracks.find((candidate) => candidate.type === type && candidate.index === index);
  if (!track) {
    const error = new Error(`The requested ${type} track does not exist in the precondition snapshot.`);
    error.code = "TARGET_NOT_FOUND";
    throw error;
  }
}

function assertSubtitleTrack(snapshot, ensureTrack = true) {
  const tracks = snapshot.tracks.filter((track) => track.type === "subtitle");
  if (tracks.length === 0) {
    if (!ensureTrack) {
      const error = new Error("The precondition snapshot has no subtitle track and track creation was disabled.");
      error.code = "TARGET_NOT_FOUND";
      throw error;
    }
  }
}

function stableTrackState(snapshot, excluded = new Set()) {
  return {
    project: snapshot.project,
    timeline: snapshot.timeline,
    frameRate: snapshot.frameRate,
    start: snapshot.start,
    markers: snapshot.markers ?? [],
    tracks: snapshot.tracks.filter((track) => !excluded.has(`${track.type}:*`) && !excluded.has(`${track.type}:${track.index}`)).map((track) => ({
      type: track.type, index: track.index, name: track.name, enabled: track.enabled, locked: track.locked,
      clips: track.clips.map(({ snapshotId: _id, snapshotTrackId: _trackId, snapshotRevision: _revision, ...clip }) => clip),
    })),
  };
}

function protectedStatePreserved(before, after, excluded) {
  return JSON.stringify(stableTrackState(before, excluded)) === JSON.stringify(stableTrackState(after, excluded));
}

function subtitleRows(response) {
  return Array.isArray(response?.data) ? response.data : [];
}

function addedSubtitleRows(beforeRows, afterRows) {
  const key = (row) => JSON.stringify([Number(row.track), Number(row.start_frame), Number(row.end_frame), String(row.text ?? "")]);
  const retained = new Map();
  for (const row of beforeRows) retained.set(key(row), (retained.get(key(row)) ?? 0) + 1);
  return afterRows.filter((row) => {
    const rowKey = key(row);
    const count = retained.get(rowKey) ?? 0;
    if (count === 0) return true;
    retained.set(rowKey, count - 1);
    return false;
  });
}

function srtCues(value, fps, timelineStart) {
  const toFrame = (timestamp) => {
    const match = /^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$/.exec(timestamp.trim());
    if (!match) return null;
    const seconds = Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) + Number(match[4]) / 1000;
    return timelineStart + Math.round(seconds * fps);
  };
  return String(value).replace(/\r\n/g, "\n").trim().split(/\n{2,}/).map((block) => {
    const lines = block.split("\n");
    const timingIndex = lines.findIndex((line) => line.includes("-->"));
    if (timingIndex < 0) return null;
    const [start, end] = lines[timingIndex].split("-->");
    return {
      text: lines.slice(timingIndex + 1).filter((line) => line.trim()).map((line) => line.trim()).join("\n"),
      startFrame: toFrame(start),
      endFrame: toFrame(end),
    };
  }).filter((cue) => cue?.text && cue.startFrame !== null && cue.endFrame !== null);
}

async function currentSnapshot(live, input) {
  const inspected = await live.readWithMutationGuard({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, { deadlineAtMs: Date.now() + 30_000 });
  const snapshot = inspected.value;
  if (snapshot.revision !== input.precondition) {
    const error = new Error("The timeline revision changed before this caption action began.");
    error.code = "STALE_REVISION";
    throw error;
  }
  return { snapshot, mutationGuard: inspected.mutationGuard };
}

function canonicalSubtitleItems(snapshot, rows, requestedTrack) {
  const canonicalTracks = snapshot.tracks.filter((track) => track.type === "subtitle" && (requestedTrack === undefined || track.index === requestedTrack));
  const expectedCount = canonicalTracks.reduce((count, track) => count + track.clips.length, 0);
  if (rows.length !== expectedCount) {
    throw new Error(`Subtitle readback returned ${rows.length} items but the canonical timeline snapshot contains ${expectedCount} matching items.`);
  }
  const offsets = new Map();
  return rows.map((row) => {
    const trackIndex = Number(row.track);
    const track = snapshot.tracks.find((candidate) => candidate.type === "subtitle" && candidate.index === trackIndex);
    if (!track) throw new Error(`Subtitle readback referenced missing canonical subtitle track ${trackIndex}.`);
    const offset = offsets.get(trackIndex) ?? 0;
    const clip = track.clips[offset];
    offsets.set(trackIndex, offset + 1);
    if (!clip || clip.recordRange.start !== Number(row.start_frame) || clip.recordRange.endExclusive !== Number(row.end_frame)) {
      throw new Error("Subtitle readback did not join the canonical timeline snapshot item order and record range.");
    }
    return {
      id: clip.snapshotId,
      trackId: track.snapshotId,
      trackIndex,
      text: String(row.text ?? ""),
      recordRange: { domain: "timeline_record_range", unit: "frames", start: Number(row.start_frame), endExclusive: Number(row.end_frame) },
    };
  });
}

function success(result, verificationReport, possibleMutation = "confirmed", usage = "not_reserved") {
  return { status: "succeeded", result, verification: verificationReport, possibleMutation, usage };
}

function transcriptResult(data, transcript) {
  const words = Array.isArray(transcript.words) ? transcript.words.map((word) => ({
    text: String(word?.text ?? ""), startSeconds: Number(word?.start ?? 0), endSeconds: Number(word?.end ?? word?.start ?? 0),
    speaker: typeof word?.speaker_id === "string" ? word.speaker_id : typeof word?.speaker === "string" ? word.speaker : null,
  })) : [];
  return {
    provider: String(data.provider || "cutagent_cloud"), model: String(data.model || "hosted_transcript"),
    languageCode: typeof transcript.language_code === "string" ? transcript.language_code : null,
    text: String(transcript.text ?? words.map((word) => word.text).join(" ").trim()), words,
    durationSeconds: Number.isFinite(Number(transcript.audio_duration)) ? Number(transcript.audio_duration) : (words.length ? Math.max(...words.map((word) => word.endSeconds)) : null),
    deliveryAcknowledged: true,
    deliveryRecovered: data.delivery_recovered === true,
  };
}

/** Build accepted caption/transcript executors over the existing CutAgent CLI and durable operation authority. */
export function createSdkCaptionActionDefinitions({ toolExecutionService, liveInspectionService, transcriptDeliveryDir, authService, transcriptBroker = null }) {
  if (typeof toolExecutionService?.executeCutAgentCliCommand !== "function" || typeof liveInspectionService?.read !== "function"
    || typeof liveInspectionService?.readWithMutationGuard !== "function"
    || typeof transcriptDeliveryDir !== "string" || !path.isAbsolute(transcriptDeliveryDir)
    || typeof authService?.capture !== "function" || typeof authService?.assertCurrent !== "function") {
    throw new TypeError("SDK caption actions require CutAgent CLI execution and live inspection authorities.");
  }
  const run = async (args, options) => envelope(await toolExecutionService.executeCutAgentCliCommand({ args, expect_json: true }, options));
  const actionDefinitions = {};
  for (const [actionId, definition] of Object.entries(definitions)) actionDefinitions[actionId] = { ...definition };
  const cancellationUnsupported = async () => ({ confirmed: false, reason: "This CutAgent CLI capability does not expose authoritative cancellation." });
  for (const definition of Object.values(actionDefinitions)) definition.cancel = cancellationUnsupported;

  actionDefinitions["cutagent.action.timeline.subtitle.list"].execute = async (_context, input) => {
    const { snapshot, mutationGuard } = await currentSnapshot(liveInspectionService, input);
    const response = await run(["timeline", "subtitle", "list", ...(input.track ? ["--track", String(input.track)] : [])], { sdkTimelineGuard: mutationGuard });
    const rows = Array.isArray(response.data) ? response.data : [];
    const items = canonicalSubtitleItems(snapshot, rows, input.track);
    return success({ timelineId: input.timelineId, revision: snapshot.revision, frameRate: snapshot.frameRate, items }, verification("Subtitle items were read from DaVinci Resolve and joined to the canonical timeline snapshot.", [evidence(`Read ${items.length} native subtitle items.`)]), "none");
  };

  actionDefinitions["cutagent.action.timeline.subtitle.insert"].execute = async (context, input) => {
    const { snapshot: before, mutationGuard } = await currentSnapshot(liveInspectionService, input);
    const beforeRows = subtitleRows(await run(["timeline", "subtitle", "list"], { sdkTimelineGuard: mutationGuard }));
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cutagent-sdk-subtitles-"));
    const subtitlePath = path.join(directory, "captions.srt");
    try {
      fs.writeFileSync(subtitlePath, input.srt, { encoding: "utf8", mode: 0o600 });
      assertSubtitleTrack(before, input.ensureTrack);
      const response = await run(
        ["timeline", "subtitle", "insert", subtitlePath, input.ensureTrack ? "--ensure-track" : "--no-ensure-track"],
        { sdkTimelineGuard: mutationGuard },
      );
      const afterInspected = await liveInspectionService.readWithMutationGuard({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, { deadlineAtMs: Date.now() + 30_000 });
      const after = afterInspected.value;
      const afterRows = subtitleRows(await run(["timeline", "subtitle", "list"], { sdkTimelineGuard: afterInspected.mutationGuard }));
      const data = response.data ?? {};
      const fps = before.frameRate.numerator / before.frameRate.denominator;
      const expectedCues = srtCues(input.srt, fps, before.start.value.value);
      const addedRows = addedSubtitleRows(beforeRows, afterRows);
      if (expectedCues.length === 0 || addedRows.length < expectedCues.length || !expectedCues.every((cue) => addedRows.some((row) => String(row.text) === cue.text && Number(row.start_frame) === cue.startFrame && Number(row.end_frame) === cue.endFrame))) {
        throw new Error("Native subtitle insertion could not be independently verified against subtitle text and timing readback.");
      }
      const preserved = protectedStatePreserved(before, after, new Set(["subtitle:*"]));
      const report = verification("Native subtitle insertion passed independent DaVinci Resolve subtitle readback.", [evidence(`Matched ${expectedCues.length} imported subtitle entries by exact text and record-frame timing.`), evidence("Compared all non-subtitle timeline structure before and after insertion.", "structural")], preserved);
      if (!preserved) throw new Error("Native subtitle insertion changed timeline state outside its declared subtitle targets.");
      return success({ matchedEntries: Number(data.matched_entries), createdTrack: Boolean(data.created_subtitle_track), verification: { revision: after.revision, evidenceCount: report.evidence.length } }, report);
    } finally { fs.rmSync(directory, { recursive: true, force: true }); }
  };

  actionDefinitions["cutagent.action.timeline.subtitle.export"].execute = async (context, input) => {
    const { snapshot: before, mutationGuard } = await currentSnapshot(liveInspectionService, input);
    const response = await run(["timeline", "subtitle", "list", ...(input.track ? ["--track", String(input.track)] : [])], { sdkTimelineGuard: mutationGuard });
    const rows = Array.isArray(response.data) ? response.data : [];
    const fps = before.frameRate.numerator / before.frameRate.denominator;
    const content = serializeSubtitles(rows, input.format, fps, before.start.value.value);
    const sha256 = crypto.createHash("sha256").update(content).digest("hex");
    const fileEvidence = evidence("Serialized subtitle bytes were derived from authoritative readback and hashed.", "file", `sha256:${sha256}`);
    return success({ format: input.format, content, exportedEntries: rows.length, sha256 }, verification("Subtitle export serialization passed authoritative subtitle readback.", [fileEvidence]), "none");
  };

  actionDefinitions["cutagent.action.timeline.auto_caption"].execute = async (context, input) => {
    const { snapshot: before, mutationGuard } = await currentSnapshot(liveInspectionService, input);
    const beforeCount = before.tracks.filter((track) => track.type === "subtitle").reduce((sum, track) => sum + track.clips.length, 0);
    context.reportProgress({ phase: "davinci_resolve_auto_caption", overallFraction: 0.2, phaseFraction: 0.1 });
    await run(
      ["timeline", "auto-caption", ...(input.language ? ["--language", input.language] : []), ...(input.preset ? ["--preset", input.preset] : []), ...(input.charsPerLine ? ["--chars-per-line", String(input.charsPerLine)] : []), ...(input.lineBreak ? ["--line-break", input.lineBreak] : []), ...(input.gap !== undefined ? ["--gap", String(input.gap)] : [])],
      { sdkTimelineGuard: mutationGuard },
    );
    const after = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, { deadlineAtMs: Date.now() + 30_000 });
    const afterCount = after.tracks.filter((track) => track.type === "subtitle").reduce((sum, track) => sum + track.clips.length, 0);
    if (afterCount <= beforeCount) throw new Error("DaVinci Resolve auto-caption did not produce verifiable subtitle items.");
    const preserved = protectedStatePreserved(before, after, new Set(["subtitle:*"]));
    const report = verification("DaVinci Resolve auto-caption produced new native subtitle items.", [evidence(`Read back ${afterCount - beforeCount} new subtitle items.`), evidence("Compared all non-subtitle timeline structure before and after auto-caption.", "structural")], preserved);
    if (!preserved) throw new Error("DaVinci Resolve auto-caption changed timeline state outside its declared subtitle targets.");
    return success({ createdItems: afterCount - beforeCount, verification: { revision: after.revision, evidenceCount: report.evidence.length } }, report);
  };

  actionDefinitions["cutagent.action.text.insert_captions"].execute = async (context, input) => {
    const { snapshot: before, mutationGuard } = await currentSnapshot(liveInspectionService, input);
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cutagent-sdk-designed-captions-"));
    const specPath = path.join(directory, "caption-spec.json");
    try {
      const fps = before.frameRate.numerator / before.frameRate.denominator;
      const transcriptPath = path.join(directory, "transcript.json");
      fs.writeFileSync(transcriptPath, JSON.stringify({ words: input.cues.map((cue) => {
        const timing = cue.timing;
        const start = timing.unit === "seconds" ? timing.start : timing.start / fps;
        const end = timing.unit === "seconds" ? timing.endExclusive : timing.endExclusive / fps;
        const timelineStartSeconds = before.start.value.value / fps;
        const loweredStart = timing.domain === "timeline_record_range" ? start - timelineStartSeconds : start;
        const loweredEnd = timing.domain === "timeline_record_range" ? end - timelineStartSeconds : end;
        if (!Number.isFinite(loweredStart) || !Number.isFinite(loweredEnd) || loweredStart < 0 || loweredEnd <= loweredStart) {
          throw new Error("Designed caption timing must lower to a non-negative, non-empty transcript-relative range.");
        }
        return { text: cue.text, start: loweredStart, end: loweredEnd };
      }) }), { encoding: "utf8", mode: 0o600 });
      const segmentation = input.segmentation;
      fs.writeFileSync(specPath, JSON.stringify({ transcript: transcriptPath, template: input.template.path, track: input.trackIndex, holder_kind: "textplus", segmentation: { unit: segmentation.unit, target: segmentation.target, preferred_min: segmentation.preferredMin, preferred_max: segmentation.preferredMax, hard_max: segmentation.hardMax, max_characters_per_line: segmentation.maxCharactersPerLine, max_lines: segmentation.maxLines, preferred_cps: segmentation.preferredCps, hard_cps: segmentation.hardCps, minimum_duration_seconds: segmentation.minimumDurationSeconds, pause_threshold_seconds: segmentation.pauseThresholdSeconds } }), { encoding: "utf8", mode: 0o600 });
      assertTrackExists(before, "video", input.trackIndex);
      const response = await run(["text", "insert-captions", "--spec", specPath], { sdkTimelineGuard: mutationGuard });
      const after = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, { deadlineAtMs: Date.now() + 30_000 });
      const created = Array.isArray(response.data?.result?.created) ? response.data.result.created : [];
      const targetTrack = after.tracks.find((track) => track.type === "video" && track.index === input.trackIndex);
      const placementsVerified = created.length > 0 && targetTrack && created.every((item) => targetTrack.clips.some((clip) => clip.recordRange.start === Number(item.record_frame) && clip.duration.value.value === Number(item.duration_frames)));
      const cliVerified = response.data?.verification?.status === "verified";
      if (!placementsVerified || !cliVerified) throw new Error("Designed caption insertion requires exact placement and Fusion/Text+ verification; the runtime returned only partial evidence.");
      const inserted = created.length;
      const preserved = protectedStatePreserved(before, after, new Set([`video:${input.trackIndex}`]));
      const report = verification("Designed Text+ captions passed exact target-track placement and command verification.", [evidence(`Read back ${inserted} exact caption placements on video track ${input.trackIndex}.`), evidence("CutAgent CLI reported verified Text+ DB/Fusion insertion and all non-target tracks were unchanged.", "structural")], preserved);
      if (!preserved) throw new Error("Designed caption insertion changed timeline state outside its declared video track.");
      return success({ insertedItems: inserted, trackIndex: input.trackIndex, verification: { revision: after.revision, evidenceCount: report.evidence.length } }, report);
    } finally { fs.rmSync(directory, { recursive: true, force: true }); }
  };

  const executeTranscript = async (context, input) => {
    const { snapshot: before, mutationGuard } = await currentSnapshot(liveInspectionService, input);
    const outputPath = path.join(transcriptDeliveryDir, `${context.operationId}.json`);
    {
      context.reportProgress({ phase: "hosted_transcription", overallFraction: 0.05, phaseFraction: 0.05 }, { waitingFor: "external_service" });
      const baseArgs = ["transcript", "create", outputPath, ...(input.languageCode ? ["--language-code", input.languageCode] : []), input.diarize ? "--diarize" : "--no-diarize", ...(input.numSpeakers ? ["--num-speakers", String(input.numSpeakers)] : []), ...input.keyterms.flatMap((term) => ["--keyterm", term]), ...(input.verbatim ? [] : ["--no-verbatim"])];
      let resumeJobId = input.resumeJobId;
      let allowNewJob = input.newJob && !resumeJobId && context.reconciling !== true;
      let response;
      for (;;) {
        try {
          const authenticated = await captureAuthenticatedSdkRequest(authService);
          if (authenticated.accountFingerprint !== context.accountFingerprint) {
            const error = new Error("The authenticated CutAgent account no longer owns this transcript operation.");
            error.code = "AUTH_SESSION_CHANGED";
            throw error;
          }
          assertAuthenticatedSdkRequestCurrent(authService, authenticated);
          const dispatched = await run(
            [...baseArgs, ...(resumeJobId ? ["--resume-job", resumeJobId] : []), ...(allowNewJob ? ["--new-job"] : []), ...(fs.existsSync(outputPath) ? ["--force"] : [])],
            {
              sdkTimelineGuard: mutationGuard,
              accessToken: authenticated.accessToken,
              issueBrokerEnvironment: ({ authorization, args }) => issueCutAgentCliBrokerEnvironment({
                broker: transcriptBroker,
                authorization,
                args,
                commandId: "transcript.create",
              }),
            },
          );
          response = dispatched;
          assertAuthenticatedSdkRequestCurrent(authService, authenticated);
          break;
        } catch (error) {
          const retryableHosted = ["HOSTED_TRANSCRIPT_PENDING", "HOSTED_TRANSCRIPT_RESUME_REQUIRED", "HOSTED_TRANSCRIPT_ATTEMPT_UNCERTAIN"].includes(error?.code);
          if (!retryableHosted) throw error;
          const retainedJobId = error?.details?.hosted_transcript_job?.job_id;
          if (typeof retainedJobId === "string" && retainedJobId) resumeJobId = retainedJobId;
          allowNewJob = false;
          context.reportProgress({ phase: "hosted_transcription", overallFraction: 0.1, phaseFraction: 0.1 }, { waitingFor: "external_service" });
          await waitForReconciliation(2_000);
        }
      }
      const transcript = JSON.parse(fs.readFileSync(outputPath, "utf8"));
      const result = transcriptResult(response.data ?? {}, transcript);
      const sha256 = crypto.createHash("sha256").update(fs.readFileSync(outputPath)).digest("hex");
      const after = await liveInspectionService.read({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, { deadlineAtMs: Date.now() + 30_000 });
      const preserved = after.revision === before.revision && protectedStatePreserved(before, after, new Set());
      const report = verification("CutAgent CLI acknowledged durable hosted transcript delivery and restored the protected timeline.", [
        evidence("Acknowledged transcript delivery bytes were read back and hashed.", "file", `sha256:${sha256}`),
        evidence("Compared the complete timeline structure before and after transcript rendering.", "structural"),
      ], preserved);
      if (!preserved) throw new Error("Hosted transcript rendering changed the protected timeline state.");
      return success(result, report, "none", "consumed");
    }
  };
  actionDefinitions["cutagent.action.transcript.create"].execute = executeTranscript;
  actionDefinitions["cutagent.action.transcript.create"].reconcile = (context, input) => executeTranscript({ ...context, reconciling: true, reportProgress() {} }, input);
  return Object.freeze(actionDefinitions);
}
