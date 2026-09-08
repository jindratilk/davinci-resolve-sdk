import crypto from "node:crypto";
import {
  sdkMediaPoolPageSchema,
  sdkColorTargetSnapshotSchema,
  sdkMulticamSnapshotSchema,
  sdkFusionCompositionReferenceSchema,
  sdkProjectReferenceSchema,
  sdkRenderDiscoverySchema,
  sdkRenderJobStatusSnapshotSchema,
  sdkRenderPresetsSchema,
  sdkRenderQueuePageSchema,
  sdkRenderSettingsSnapshotSchema,
  sdkRetimeReadbackSchema,
  sdkTimelineReferenceSchema,
  sdkTimelineSnapshotSchema,
  sdkTimelineEditImpactSchema,
} from "../contracts/generated/sdk-runtime.js";
import { sdkStableMutationTargetSchema } from "../contracts/generated/sdk-mutation-policy.js";
import { sdkProjectContextObservationSchema } from "../contracts/generated/sdk-project-media.js";

const DEFAULT_INTERNAL_INSPECTION_TIMEOUT_MS = 60_000;

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]),
  );
}

function digest(prefix, value) {
  const payload = JSON.stringify(canonicalize(value));
  return `${prefix}f${crypto.createHash("sha256").update(payload, "utf8").digest("base64url")}`;
}

function opaque(prefix, value) {
  return `${prefix}${crypto.createHash("sha256").update(value, "utf8").digest("hex").slice(0, 32)}`;
}

export function projectSdkMediaPoolItemIdentity(projectId, nativeId) {
  const normalizedProjectId = text(projectId);
  const normalizedNativeId = text(nativeId);
  if (!normalizedProjectId || !normalizedNativeId) return null;
  return digest("media_pool_item_", {
    projectId: normalizedProjectId,
    nativeId: normalizedNativeId,
  });
}

export function projectSdkMediaPoolFolderIdentity(projectId, nativeId) {
  const normalizedProjectId = text(projectId);
  const normalizedNativeId = text(nativeId);
  if (!normalizedProjectId || !normalizedNativeId) return null;
  return digest("media_pool_folder_", {
    projectId: normalizedProjectId,
    nativeId: normalizedNativeId,
  });
}

function privateEvidenceDigest(key, value) {
  const payload = JSON.stringify(canonicalize(value));
  return crypto.createHmac("sha256", key).update(payload, "utf8").digest("base64url");
}

function privateTextDigest(value) {
  return `sha256:${crypto.createHash("sha256").update(value, "utf8").digest("hex")}`;
}

function managedMediaEntry(entry) {
  const stable = { ...entry };
  delete stable.selected;
  return stable;
}

function text(value) {
  return typeof value === "string" ? value.trim() : "";
}

function nullableRenderText(value, maximum = 1024) {
  const normalized = text(value);
  return normalized && normalized.length <= maximum ? normalized : null;
}

function plainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function publicRenderLabel(value, fallback) {
  const normalized = nullableRenderText(value);
  if (!normalized || /[\\/]/.test(normalized) || /^[A-Za-z]:/.test(normalized) || /^file:/i.test(normalized)) {
    return fallback;
  }
  return normalized;
}

const KNOWN_RENDER_FORMATS = new Map([
  ["quicktime", "quicktime"], ["mov", "quicktime"], ["mp4", "mp4"], ["mpeg4", "mp4"],
  ["mxf", "mxf"], ["wave", "wave"], ["wav", "wave"], ["aiff", "aiff"], ["aif", "aiff"],
  ["dcp", "dcp"], ["exr", "image_sequence"], ["dpx", "image_sequence"], ["tiff", "image_sequence"],
  ["tif", "image_sequence"], ["jpeg", "image_sequence"], ["jpg", "image_sequence"], ["png", "image_sequence"],
]);
const KNOWN_RENDER_CODECS = new Map([
  ["h264", "h264"], ["avc", "h264"], ["h265", "h265"], ["hevc", "h265"],
  ["appleprores", "prores"], ["prores", "prores"], ["dnxhr", "dnxhr"], ["dnxhd", "dnxhr"],
  ["av1", "av1"], ["linearpcm", "linear_pcm"], ["lpcm", "linear_pcm"], ["pcm", "linear_pcm"],
  ["aac", "aac"], ["flac", "flac"], ["exr", "exr"], ["dpx", "dpx"], ["tiff", "tiff"],
  ["tif", "tiff"], ["jpeg", "jpeg"], ["jpg", "jpeg"],
]);
const KNOWN_RENDER_CODEC_VARIANT_PREFIXES = new Set(["appleprores", "prores", "dnxhr", "dnxhd"]);

function normalizedToken(value) {
  return text(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function versionedValue(value, knownValues, variantPrefixes = new Set()) {
  const label = text(value);
  const token = normalizedToken(label);
  const known = knownValues.get(token)
    ?? [...knownValues.entries()].find(([candidate]) => (
      variantPrefixes.has(candidate) && token.startsWith(candidate)
    ))?.[1];
  return known ? { kind: "known", value: known } : { kind: "unknown_version", label: label || "unknown" };
}

function renderSupport(value) {
  if (value === "supported") return { availability: "supported" };
  if (value === "unavailable") return { availability: "unavailable", reason: "api_unavailable" };
  if (value === "unknown_version") return { availability: "unknown_version", reason: "unrecognized_response" };
  return malformed("CutAgent CLI omitted explicit render capability truth.");
}

function renderProject(raw, identityNamespace) {
  if (!raw || typeof raw !== "object") return malformed("CutAgent CLI returned malformed render context.");
  if (raw.project_open === false) {
    throw new SdkLiveInspectionError("STALE_REVISION", "The referenced DaVinci Resolve project is no longer open.");
  }
  if (raw.project_open !== true) return malformed("CutAgent CLI did not prove the render project open state.");
  const nativeId = text(raw.project_id);
  const name = text(raw.project_name);
  if (!nativeId || !name) return malformed("CutAgent CLI did not prove an authoritative render project identity.");
  return parseRuntime(sdkProjectReferenceSchema, {
    id: digest("project_", { identityNamespace, nativeId }),
    name,
  }, "CutAgent CLI returned an invalid render project identity.");
}

function normalizeRenderDiscovery(raw, projectId) {
  if (!plainObject(raw) || !Array.isArray(raw.formats)) return malformed("CutAgent CLI returned malformed render format inventory.");
  const formats = raw.formats.map((format) => {
    if (!plainObject(format) || !Array.isArray(format.codecs)) return malformed("CutAgent CLI returned a malformed render format row.");
    const extension = publicRenderLabel(format.extension, null);
    const formatLabel = publicRenderLabel(format.label, extension ?? "unknown");
    const formatValue = versionedValue(formatLabel, KNOWN_RENDER_FORMATS);
    const codecs = format.codecs.map((codec) => {
      if (!plainObject(codec) || !Array.isArray(codec.resolutions)) return malformed("CutAgent CLI returned a malformed render codec row.");
      const codecApiValue = publicRenderLabel(codec.api_value, "unknown");
      const codecLabel = publicRenderLabel(codec.label, codecApiValue);
      return {
        codec: versionedValue(
          codecLabel,
          KNOWN_RENDER_CODECS,
          KNOWN_RENDER_CODEC_VARIANT_PREFIXES,
        ),
        label: codecLabel,
        resolutionSupport: renderSupport(codec.resolution_support),
        resolutions: codec.resolutions.map((resolution) => {
          if (!plainObject(resolution)) return malformed("CutAgent CLI returned a malformed render resolution row.");
          return { width: integer(resolution.width), height: integer(resolution.height) };
        }),
      };
    });
    if (codecs.length === 0
      && format.codec_support === "supported"
      && formatValue.kind === "known"
      && formatValue.value === "wave") {
      codecs.push({
        codec: { kind: "known", value: "linear_pcm" },
        label: "Linear PCM",
        resolutionSupport: { availability: "supported" },
        resolutions: [],
      });
    }
    return {
      format: formatValue,
      label: formatLabel,
      extension,
      codecSupport: renderSupport(format.codec_support),
      codecs,
    };
  });
  return parseRuntime(sdkRenderDiscoverySchema, {
    projectId,
    formatSupport: renderSupport(raw?.format_support),
    formats,
  }, "CutAgent CLI returned render discovery data that violated the SDK contract.");
}

function normalizeRenderPresets(raw, projectId) {
  if (!plainObject(raw) || !Array.isArray(raw.presets)) return malformed("CutAgent CLI returned malformed render preset inventory.");
  return parseRuntime(sdkRenderPresetsSchema, {
    projectId,
    support: renderSupport(raw.support),
    presets: raw.presets.map((name) => ({ name: text(name) })),
  }, "CutAgent CLI returned render preset data that violated the SDK contract.");
}

function pickSetting(settings, ...keys) {
  for (const key of keys) {
    if (settings && Object.prototype.hasOwnProperty.call(settings, key)) return settings[key];
  }
  return null;
}

function nullableBoolean(value) {
  if (typeof value === "boolean") return value;
  if (value === 1 || value === "1" || String(value).toLowerCase() === "true") return true;
  if (value === 0 || value === "0" || String(value).toLowerCase() === "false") return false;
  return null;
}

function normalizeRenderSettings(raw, projectId) {
  if (!plainObject(raw) || !plainObject(raw.settings) || !plainObject(raw.format_codec)) {
    return malformed("CutAgent CLI returned malformed render settings.");
  }
  const settings = raw.settings;
  const formatCodec = raw.format_codec;
  const format = pickSetting(formatCodec, "format", "Format", "format_name", "FormatName")
    ?? pickSetting(settings, "format", "Format", "FormatName");
  const codec = pickSetting(formatCodec, "codec", "Codec", "codec_name", "CodecName")
    ?? pickSetting(settings, "codec", "Codec", "CodecName");
  const publicFormat = publicRenderLabel(format, null);
  const publicCodec = publicRenderLabel(codec, null);
  const width = integer(pickSetting(settings, "FormatWidth", "format_width", "Width"));
  const height = integer(pickSetting(settings, "FormatHeight", "format_height", "Height"));
  const frameRate = finiteNumber(pickSetting(settings, "FrameRate", "frame_rate", "fps"));
  const modeValue = raw?.mode;
  const mode = modeValue === 0 || modeValue === "0"
    ? { kind: "known", value: "individual_clips" }
    : modeValue === 1 || modeValue === "1"
      ? { kind: "known", value: "single_clip" }
      : modeValue === null || modeValue === undefined
        ? null
        : { kind: "unknown_version", value: String(modeValue).slice(0, 128) };
  const selectAllFrames = nullableBoolean(pickSetting(settings, "SelectAllFrames", "select_all_frames"));
  const markInFrame = integer(pickSetting(settings, "MarkIn", "mark_in", "MarkInFrame"));
  const markOutFrame = integer(pickSetting(settings, "MarkOut", "mark_out", "MarkOutFrame"));
  const range = selectAllFrames === true
    ? { kind: "full_timeline" }
    : markInFrame !== null && markOutFrame !== null && markOutFrame >= markInFrame
      ? { kind: "custom", markInFrame, markOutFrame }
      : { kind: "unknown" };
  const sanitized = {
    projectId,
    support: renderSupport(raw?.support),
    format: publicFormat === null ? null : versionedValue(publicFormat, KNOWN_RENDER_FORMATS),
    codec: publicCodec === null ? null : versionedValue(
      publicCodec,
      KNOWN_RENDER_CODECS,
      KNOWN_RENDER_CODEC_VARIANT_PREFIXES,
    ),
    resolution: width && height ? { width, height } : null,
    frameRate: frameRate !== null && frameRate > 0 ? frameRate : null,
    mode,
    range,
    exportVideo: nullableBoolean(pickSetting(settings, "ExportVideo", "export_video")),
    exportAudio: nullableBoolean(pickSetting(settings, "ExportAudio", "export_audio")),
    exportSubtitles: nullableBoolean(pickSetting(settings, "ExportSubtitle", "export_subtitle")),
    customName: publicRenderLabel(pickSetting(settings, "CustomName", "custom_name"), null),
    queueCount: 0,
  };
  return sanitized;
}

function statusValue(rawJob) {
  const status = rawJob?.status && typeof rawJob.status === "object" ? rawJob.status : {};
  const job = rawJob?.job && typeof rawJob.job === "object" ? rawJob.job : {};
  const value = text(status.JobStatus || status.RenderJobStatus || status.Status || status.status
    || job.RenderJobStatus || job.JobStatus || job.Status || job.status);
  const normalized = normalizedToken(value);
  const known = new Map([
    ["queued", "queued"], ["ready", "queued"], ["rendering", "rendering"], ["inprogress", "rendering"],
    ["complete", "completed"], ["completed", "completed"], ["success", "completed"], ["succeeded", "completed"],
    ["failed", "failed"], ["error", "failed"], ["cancelled", "cancelled"], ["canceled", "cancelled"], ["aborted", "cancelled"],
  ]).get(normalized);
  return known ? { kind: "known", value: known } : { kind: "unknown_version", value: value || "unknown" };
}

function progressValue(rawJob) {
  const status = rawJob?.status && typeof rawJob.status === "object" ? rawJob.status : {};
  const job = rawJob?.job && typeof rawJob.job === "object" ? rawJob.job : {};
  const raw = status.CompletionPercentage ?? status.Progress ?? status.progress
    ?? job.CompletionPercentage ?? job.Progress ?? job.progress;
  const value = finiteNumber(raw);
  return value !== null && value >= 0 && value <= 100 ? value : null;
}

function renderJobConfigurationMatches(rawJob, expected) {
  if (!plainObject(rawJob) || !plainObject(expected)) return false;
  const knownFormat = versionedValue(
    publicRenderLabel(rawJob.VideoFormat, null)
      ?? publicRenderLabel(rawJob.AudioFormat, null)
      ?? publicRenderLabel(rawJob.Format, null),
    KNOWN_RENDER_FORMATS,
  );
  const knownCodec = versionedValue(
    publicRenderLabel(rawJob.VideoCodec, null)
      ?? publicRenderLabel(rawJob.AudioCodec, null)
      ?? publicRenderLabel(rawJob.Codec, null),
    KNOWN_RENDER_CODECS,
    KNOWN_RENDER_CODEC_VARIANT_PREFIXES,
  );
  const mode = String(rawJob.RenderMode ?? "").trim().toLowerCase().replaceAll("_", " ");
  const targetDir = nullableRenderText(rawJob.TargetDir, 8192);
  const outputFilename = nullableRenderText(rawJob.OutputFilename ?? rawJob.OutputFileName, 4096);
  return targetDir === expected.targetDir
    && outputFilename === expected.outputFilename
    && knownFormat?.kind === "known" && knownFormat.value === expected.format
    && knownCodec?.kind === "known" && knownCodec.value === expected.codec
    && nullableBoolean(rawJob.IsExportVideo ?? rawJob.ExportVideo) === expected.exportVideo
    && nullableBoolean(rawJob.IsExportAudio ?? rawJob.ExportAudio) === expected.exportAudio
    && (expected.width === null || (
      integer(rawJob.FormatWidth) === expected.width
      && integer(rawJob.FormatHeight) === expected.height
    ))
    && (expected.frameRate === null || (
      finiteNumber(rawJob.FrameRate) !== null
      && Math.abs(finiteNumber(rawJob.FrameRate) - expected.frameRate) <= 0.01
    ))
    && ["single", "single clip", "1"].includes(mode)
    && integer(rawJob.MarkIn) === expected.markInFrame
    && integer(rawJob.MarkOut) === expected.markOutFrame;
}

function queueState(raw, projectId, identityEvidenceKey) {
  if (!plainObject(raw) || !Array.isArray(raw.jobs)) return malformed("CutAgent CLI returned malformed render queue inventory.");
  const support = renderSupport(raw.support);
  if (support.availability !== "supported" && raw.jobs.length > 0) return malformed("CutAgent CLI returned jobs for an unavailable render queue.");
  const nativeIds = new Set();
  const structural = raw.jobs.map((row, offset) => {
    if (!plainObject(row) || !plainObject(row.job)) return malformed("CutAgent CLI returned a malformed render queue row.");
    if (!Number.isSafeInteger(row.index) || row.index !== offset + 1) {
      return malformed("CutAgent CLI returned an invalid render queue coordinate.");
    }
    const nativeId = nullableRenderText(row.native_id, 1024);
    if (!nativeId) return malformed("CutAgent CLI returned a render job without authoritative native identity.");
    if (nativeIds.has(nativeId)) return malformed("CutAgent CLI returned duplicate native render job identity.");
    nativeIds.add(nativeId);
    const statusSupport = renderSupport(row.status_support);
    if (statusSupport.availability === "supported" && !plainObject(row.status)) {
      return malformed("CutAgent CLI returned render job status without structured evidence.");
    }
    return {
      index: row.index,
      nativeId,
      name: publicRenderLabel(row.job.CustomName ?? row.job.TimelineName, `Render job ${offset + 1}`),
      statusSupport,
    };
  });
  const queueRevision = digest("revision_", {
    projectId,
    structural: structural.map(({ index, nativeId, name }) => ({
      index,
      name,
      nativeIdentityEvidence: privateEvidenceDigest(identityEvidenceKey, { projectId, nativeId }),
    })),
  });
  const jobs = raw.jobs.map((row, offset) => ({
    id: digest("snapshot_render_job_", {
      queueRevision,
      index: structural[offset]?.index,
      nativeIdentityEvidence: privateEvidenceDigest(identityEvidenceKey, {
        projectId,
        nativeId: structural[offset]?.nativeId,
      }),
    }),
    projectId,
    queueRevision,
    index: structural[offset]?.index,
    name: structural[offset]?.name,
    statusSupport: structural[offset]?.statusSupport,
    status: statusValue(row),
    progressPercent: progressValue(row),
  }));
  return { queueRevision, jobs, support };
}

function cursorToken(key, queueRevision, offset) {
  const payload = `${queueRevision}.${offset}`;
  const signature = crypto.createHmac("sha256", key).update(payload, "utf8").digest("base64url");
  return `render_queue_cursor_${payload}.${signature}`;
}

function parseCursor(key, cursor, queueRevision) {
  if (cursor === null) return 0;
  const match = /^render_queue_cursor_([A-Za-z0-9._~-]+)\.([A-Za-z0-9_-]+)$/.exec(String(cursor));
  if (!match) return malformed("The render queue cursor is malformed.");
  const expected = crypto.createHmac("sha256", key).update(match[1], "utf8").digest("base64url");
  const suppliedBuffer = Buffer.from(match[2]);
  const expectedBuffer = Buffer.from(expected);
  if (suppliedBuffer.length !== expectedBuffer.length || !crypto.timingSafeEqual(suppliedBuffer, expectedBuffer)) {
    return malformed("The render queue cursor is invalid.");
  }
  const payloadMatch = /^(revision_[A-Za-z0-9._~-]+)\.(\d+)$/.exec(match[1]);
  if (!payloadMatch) return malformed("The render queue cursor is malformed.");
  if (payloadMatch[1] !== queueRevision) throw new SdkLiveInspectionError("STALE_REVISION", "The render queue changed after this page cursor was issued.");
  const offset = integer(payloadMatch[2]);
  if (offset === null || offset < 0) return malformed("The render queue cursor offset is invalid.");
  return offset;
}

function integer(value) {
  const normalized = finiteNumber(value);
  return Number.isSafeInteger(normalized) ? normalized : null;
}

function strictInteger(value) {
  return typeof value === "number" && Number.isSafeInteger(value) ? value : null;
}

function finiteNumber(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string" || !/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value)) return null;
  const normalized = Number(value);
  return Number.isFinite(normalized) ? normalized : null;
}

function normalizedRecordSubframes(rawClip, startFrame, endFrame, durationFrames) {
  if (rawClip.record_subframes === undefined) return null;
  const raw = rawClip.record_subframes;
  if (!plainObject(raw) || Object.keys(raw).sort().join(",") !== "duration,end_exclusive,start") {
    return malformed("CutAgent CLI returned malformed private clip subframe geometry.");
  }
  const start = typeof raw.start === "number" && Number.isFinite(raw.start) ? raw.start : null;
  const endExclusive = typeof raw.end_exclusive === "number" && Number.isFinite(raw.end_exclusive) ? raw.end_exclusive : null;
  const duration = typeof raw.duration === "number" && Number.isFinite(raw.duration) ? raw.duration : null;
  if (start === null || endExclusive === null || duration === null || endExclusive <= start
    || Math.abs(duration - (endExclusive - start)) > 1e-6) {
    return malformed("CutAgent CLI returned inconsistent private clip subframe geometry.");
  }
  const projectedStart = Math.floor(start + 0.5);
  const projectedEnd = Math.max(projectedStart + 1, Math.floor(endExclusive + 0.5));
  if (!Number.isSafeInteger(projectedStart) || !Number.isSafeInteger(projectedEnd)
    || projectedStart !== startFrame || projectedEnd !== endFrame
    || durationFrames !== projectedEnd - projectedStart) {
    return malformed("CutAgent CLI returned clip frame boundaries that do not match its private subframe geometry.");
  }
  return {start, endExclusive, duration};
}

function fairlightSequenceOutputGain(value) {
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, Math.abs(value), false);
  const bits = view.getBigUint64(0, false);
  const exponentBits = Number((bits >> 52n) & 0x7ffn);
  const fraction = bits & ((1n << 52n) - 1n);
  const significand = exponentBits === 0 ? fraction : fraction | (1n << 52n);
  const exponent = (exponentBits === 0 ? -1022 : exponentBits - 1023) - 52;
  let numerator = significand * 10n;
  let denominator = 1n;
  if (exponent >= 0) numerator <<= BigInt(exponent);
  else denominator <<= BigInt(-exponent);
  let rounded = numerator / denominator;
  const remainder = numerator % denominator;
  if (remainder * 2n > denominator || (remainder * 2n === denominator && rounded % 2n === 1n)) {
    rounded += 1n;
  }
  return (value < 0 ? -Number(rounded) : Number(rounded)) / 10;
}

function gcd(left, right) {
  let a = Math.abs(left);
  let b = Math.abs(right);
  while (b !== 0) [a, b] = [b, a % b];
  return a || 1;
}

function frameRate(value) {
  const numeric = finiteNumber(value);
  if (numeric === null || numeric <= 0 || numeric > 1000) {
    throw new SdkLiveInspectionError("INVALID_RESPONSE", "DaVinci Resolve returned an invalid timeline frame rate.");
  }
  const broadcast = [
    [23.976, 24_000, 1001],
    [29.97, 30_000, 1001],
    [47.952, 48_000, 1001],
    [59.94, 60_000, 1001],
    [95.904, 96_000, 1001],
    [119.88, 120_000, 1001],
  ].find(([label]) => Math.abs(numeric - label) < 0.0006);
  let numerator;
  let denominator;
  if (broadcast) {
    [, numerator, denominator] = broadcast;
  } else {
    const source = String(value).trim();
    const decimal = /^\d+(?:\.(\d{1,6}))?$/.exec(source);
    if (!decimal) {
      throw new SdkLiveInspectionError("INVALID_RESPONSE", "DaVinci Resolve returned an unsupported timeline frame rate.");
    }
    const precision = decimal[1]?.length ?? 0;
    denominator = 10 ** precision;
    numerator = Math.round(numeric * denominator);
    const divisor = gcd(numerator, denominator);
    numerator /= divisor;
    denominator /= divisor;
  }
  return {
    numerator,
    denominator,
    nominalTimebase: Math.ceil(numerator / denominator),
  };
}

export class SdkLiveInspectionError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "SdkLiveInspectionError";
    this.code = code;
  }
}

function isLinkedAudioTrimReleaseGate(error, intent) {
  return intent?.action === "trim"
    && intent?.linkedAudio === "preserve"
    && error?.name === "BridgeCliError"
    && error?.bridge_error_type === "cutagent_cli_error"
    && error?.cli_error_code === "VALIDATION_ERROR"
    && error?.cli_error_details?.reason === "edit_trim_linked_audio_preservation_release_gated"
    && error?.cli_error_details?.mutation_started === false;
}

function isUnrepresentableSourceBoundary(error) {
  return error?.name === "BridgeCliError"
    && error?.bridge_error_type === "cutagent_cli_error"
    && error?.cli_error_code === "INVALID_TIME_REFERENCE"
    && error?.cli_error_details?.reason === "source_boundary_not_representable";
}

function isUnsupportedPartialOverwriteEdge(error, intent) {
  if (intent?.action !== "overwrite"
    || error?.name !== "BridgeCliError"
    || error?.bridge_error_type !== "cutagent_cli_error") {
    return false;
  }
  const reason = error?.cli_error_details?.reason;
  return (error?.cli_error_code === "READINESS_FAILED"
      && new Set([
        "edge_db_state_undecodable",
        "edge_db_state_unavailable",
        "edge_db_item_state_unavailable",
      ]).has(reason))
    || (error?.cli_error_code === "TIMELINE_CONFLICT"
      && new Set([
        "edge_preservation_unsupported",
        "edge_state_preservation_unsupported",
      ]).has(reason));
}

function malformed(message) {
  throw new SdkLiveInspectionError("INVALID_RESPONSE", message);
}

function parseRuntime(schema, value, message) {
  const parsed = schema.safeParse(value);
  if (!parsed.success) return malformed(message);
  return parsed.data;
}

function currentProject(identity, identityNamespace) {
  if (!identity || typeof identity !== "object" || !identity.project || typeof identity.project !== "object") {
    return malformed("CutAgent CLI returned malformed project inspection data.");
  }
  const project = identity.project;
  if (project.project_open === false || project.context === "project_manager") {
    throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "No DaVinci Resolve project is currently open.");
  }
  if (project.project_open !== true || project.context !== "project") {
    return malformed("CutAgent CLI did not prove the current project state.");
  }
  const name = text(project.name);
  if (!name) return malformed("CutAgent CLI returned a current project without a name.");
  const projectNativeId = text(project.project_id);
  if (!projectNativeId) return malformed("CutAgent CLI did not return an authoritative current project identity.");
  return parseRuntime(sdkProjectReferenceSchema, {
    id: digest("project_", { identityNamespace, nativeId: projectNativeId }),
    name,
  }, "CutAgent CLI returned an invalid current project identity.");
}

function projectContext(identity, identityNamespace) {
  const rawLibrary = identity?.library ?? (identity?.database && typeof identity.database === "object"
    ? {
        name: identity.database.database_name,
        kind: String(identity.database.database_type ?? "").trim().toLowerCase(),
      }
    : null);
  const library = rawLibrary === null || rawLibrary === undefined
    ? null
    : rawLibrary && typeof rawLibrary === "object"
      && typeof rawLibrary.name === "string" && rawLibrary.name.trim()
      && new Set(["disk", "postgresql"]).has(rawLibrary.kind)
      ? { name: rawLibrary.name.trim(), kind: rawLibrary.kind }
      : malformed("CutAgent CLI returned malformed project-library identity data.");
  const projectOpen = identity?.project?.project_open === true && identity?.project?.context === "project";
  const project = projectOpen ? currentProject(identity, identityNamespace) : null;
  let timeline = null;
  if (project !== null && text(identity.project?.current_timeline)) {
    const reference = currentTimeline(identity, project).reference;
    timeline = { id: reference.id, name: reference.name };
  }
  return parseRuntime(sdkProjectContextObservationSchema, {
    library,
    project,
    timeline,
    projectRevision: {
      status: "available",
      revision: digest("revision_", { identityNamespace, context: identity }),
    },
  }, "CutAgent CLI returned invalid project-context identity data.");
}

function privateProjectLibraryIdentity(identity) {
  const normalize = (candidate) => {
    if (!candidate || typeof candidate !== "object") return null;
    const name = text(candidate.name ?? candidate.database_name);
    const kind = text(candidate.kind ?? candidate.database_type)?.toLowerCase();
    if (!name || !new Set(["disk", "postgresql"]).has(kind)) return malformed("CutAgent CLI omitted the exact native project-library identity.");
    if (kind === "disk") return {name, kind};
    const address = text(candidate.address ?? candidate.IpAddress ?? candidate.ip_address);
    if (!address) return malformed("CutAgent CLI omitted the exact PostgreSQL project-library address.");
    return {name, kind, address};
  };
  const supplied = [identity?.library, identity?.database].filter((candidate) => candidate && typeof candidate === "object").map(normalize);
  if (supplied.length === 0) return malformed("CutAgent CLI omitted the exact native project-library identity.");
  const canonical = supplied.map((candidate) => JSON.stringify(candidate));
  if (new Set(canonical).size !== 1) return malformed("CutAgent CLI returned ambiguous native project-library identities.");
  return supplied[0];
}

function nativeProjectLibraryFromDatabase(candidate) {
  if (!candidate || typeof candidate !== "object") return malformed("CutAgent CLI returned a malformed native project-library record.");
  const dbType = text(candidate.DbType);
  const dbName = text(candidate.DbName);
  if (!dbName || !new Set(["Disk", "PostgreSQL"]).has(dbType)) {
    return malformed("CutAgent CLI returned an incomplete native project-library record.");
  }
  if (dbType === "Disk") return {name: dbName, kind: "disk"};
  const address = text(candidate.IpAddress);
  if (!address) return malformed("CutAgent CLI omitted a PostgreSQL project-library address.");
  return {name: dbName, kind: "postgresql", address};
}

function privateProjectLibraryInventory(identity, identityNamespace, currentLibrary) {
  const raw = identity?.project_libraries;
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.databases) || raw.databases.length > 1024) {
    return malformed("CutAgent CLI returned an invalid or unbounded project-library inventory.");
  }
  const currentDatabase = raw.current_database;
  const currentNative = nativeProjectLibraryFromDatabase(currentDatabase);
  if (JSON.stringify(canonicalize(currentNative)) !== JSON.stringify(canonicalize(currentLibrary))) {
    return malformed("CutAgent CLI project-library inventory disagreed with the current library identity.");
  }
  const databases = raw.databases.map((database) => {
    const nativeProjectLibrary = nativeProjectLibraryFromDatabase(database);
    return {
      stableId: digest("project_library_", {identityNamespace, library: nativeProjectLibrary}),
      nativeProjectLibrary,
      database: Object.fromEntries(["DbType", "DbName", "IpAddress"]
        .filter((key) => Object.hasOwn(database, key)).map((key) => [key, database[key]])),
    };
  }).sort((left, right) => Buffer.compare(
    Buffer.from(JSON.stringify(canonicalize(left.database)), "utf8"),
    Buffer.from(JSON.stringify(canonicalize(right.database)), "utf8"),
  ));
  const databaseKeys = databases.map((row) => JSON.stringify(canonicalize(row.database)));
  if (new Set(databaseKeys).size !== databases.length
    || databases.filter((row) => JSON.stringify(canonicalize(row.nativeProjectLibrary)) === JSON.stringify(canonicalize(currentLibrary))).length !== 1) {
    return malformed("CutAgent CLI returned ambiguous project-library inventory identities.");
  }
  return {currentDatabase: structuredClone(currentDatabase), databases};
}

function currentTimeline(identity, project) {
  if (!Array.isArray(identity?.timelines)) {
    return malformed("CutAgent CLI returned malformed timeline inventory data.");
  }
  const currentName = text(identity.project?.current_timeline);
  if (!currentName) {
    throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The current DaVinci Resolve project has no active timeline.");
  }
  const marked = identity.timelines.filter((row) => (
    row
    && typeof row === "object"
    && (row.is_current === true || text(row.current).toLowerCase() === "yes")
  ));
  if (marked.length === 0) {
    return malformed("CutAgent CLI did not prove the active timeline in the live inventory.");
  }
  if (marked.length > 1) {
    throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "The active DaVinci Resolve timeline is not uniquely identifiable.");
  }
  const match = marked[0];
  if (text(match.name) !== currentName) {
    return malformed("CutAgent CLI returned conflicting active timeline evidence.");
  }
  const nativeId = text(match.timeline_id);
  if (!nativeId) return malformed("CutAgent CLI did not return an authoritative active timeline identity.");
  const duplicateNativeIds = identity.timelines.filter((row) => row && typeof row === "object" && text(row.timeline_id) === nativeId);
  if (duplicateNativeIds.length > 1) {
    throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned an ambiguous native timeline identity.");
  }
  const index = integer(match.index);
  if (index === null || index < 1) return malformed("CutAgent CLI returned an invalid one-based timeline index.");
  const reference = parseRuntime(sdkTimelineReferenceSchema, {
    id: digest("timeline_", { projectId: project.id, nativeId }),
    projectId: project.id,
    name: currentName,
  }, "CutAgent CLI returned an invalid current timeline identity.");
  return { reference, nativeId };
}

function liveIdentity(identity, identityNamespace) {
  const project = currentProject(identity, identityNamespace);
  const timelineIdentity = currentTimeline(identity, project);
  // currentProject already requires this exact native identity. Retain it only
  // on the private inspection carrier so one bracketed snapshot can also own
  // the execution binding without a second native timeline-current read.
  const projectNativeId = text(identity.project?.project_id);
  return { project, timeline: timelineIdentity.reference, projectNativeId, timelineNativeId: timelineIdentity.nativeId };
}

function booleanSymbol(value, kind) {
  if (typeof value === "boolean") return value;
  if (value === null || value === undefined || value === "") return null;
  if (value === "✓") return true;
  if (value === "✗") return false;
  if (value === "🔒" && kind === "locked") return true;
  return null;
}

function normalizeFairlightReadback(raw) {
  const unavailable = () => ({ status: "unavailable", reason: "readback_unavailable" });
  if (raw === null || raw === undefined) {
    return {
      status: "unavailable",
      reason: "not_exposed_by_runtime",
      tracks: [],
      buses: { status: "unavailable", reason: "not_exposed_by_runtime", buses: [] },
    };
  }
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.tracks) || !raw.buses || typeof raw.buses !== "object") {
    return malformed("CutAgent CLI returned malformed Fairlight snapshot data.");
  }
  const numericReadback = (value, minimum, maximum) => {
    if (!value || typeof value !== "object" || !new Set(["available", "unavailable"]).has(value.status)) {
      return malformed("CutAgent CLI returned malformed Fairlight numeric readback data.");
    }
    if (value.status === "unavailable") return unavailable();
    if (typeof value.value !== "number" || !Number.isFinite(value.value) || value.value < minimum || value.value > maximum) {
      return malformed("CutAgent CLI returned an invalid Fairlight numeric readback value.");
    }
    return { status: "available", value: value.value };
  };
  const tracks = raw.tracks.map((track) => {
    const trackIndex = integer(track?.track_index);
    if (trackIndex === null || trackIndex < 1 || trackIndex > 4096) {
      return malformed("CutAgent CLI returned an invalid Fairlight track readback identity.");
    }
    return {
      trackIndex,
      levelDb: numericReadback(track.level_db, -160, 60),
      pan: numericReadback(track.pan, -1, 1),
    };
  });
  if (raw.buses.status === "unavailable") {
    return { status: "available", tracks, buses: { status: "unavailable", reason: "readback_unavailable", buses: [] } };
  }
  if (raw.buses.status !== "available" || !Array.isArray(raw.buses.buses)) {
    return malformed("CutAgent CLI returned malformed Fairlight bus readback data.");
  }
  const buses = raw.buses.buses.map((bus) => {
    const name = text(bus?.name);
    const kind = bus?.kind;
    if (!name || name.length > 256 || !new Set(["main", "bus"]).has(kind)) {
      return malformed("CutAgent CLI returned an invalid Fairlight bus identity.");
    }
    return { name, kind };
  });
  return { status: "available", tracks, buses: { status: "available", buses } };
}

function normalizePrivateFairlightPlanReadback(raw, privateTimelineItemNativeIdByPublicId, snapshot) {
  const planReadback = raw?.plan_readback;
  if (!plainObject(planReadback) || planReadback.status !== "available" || !Array.isArray(planReadback.clips)) {
    return {status: "unavailable", clips: [], tracks: []};
  }
  const publicIdByNativeId = new Map(
    [...privateTimelineItemNativeIdByPublicId.entries()].map(([publicId, nativeId]) => [nativeId, publicId]),
  );
  const seen = new Set();
  const optionalNumber = (value, minimum, maximum, label) => {
    if (value === null || value === undefined) return null;
    const normalized = finiteNumber(value);
    if (normalized === null || normalized < minimum || normalized > maximum) {
      return malformed(`CutAgent CLI returned an invalid private Fairlight ${label} readback.`);
    }
    return normalized;
  };
  const optionalFrames = (value, label) => {
    if (value === null || value === undefined) return null;
    const normalized = integer(value);
    if (normalized === null || normalized < 0) {
      return malformed(`CutAgent CLI returned an invalid private Fairlight ${label} readback.`);
    }
    return normalized;
  };
  const clips = planReadback.clips.map((row) => {
    const nativeId = text(row?.item_id);
    const stableId = publicIdByNativeId.get(nativeId);
    const trackIndex = integer(row?.track_index);
    if (!nativeId || !stableId || seen.has(nativeId) || trackIndex === null || trackIndex < 1) {
      return malformed("CutAgent CLI returned ambiguous private Fairlight clip-state readback.");
    }
    seen.add(nativeId);
    if (!Object.hasOwn(row, "gain_db") || row.gain_db === undefined) {
      return malformed("CutAgent CLI omitted private Fairlight clip gain readback.");
    }
    if (!Object.hasOwn(row, "fade_in_frames") || row.fade_in_frames === undefined
      || !Object.hasOwn(row, "fade_out_frames") || row.fade_out_frames === undefined) {
      return malformed("CutAgent CLI omitted private Fairlight clip fade readback.");
    }
    const effectPluginIds = row.effect_plugin_ids === null || row.effect_plugin_ids === undefined
      ? null
      : row.effect_plugin_ids;
    if (effectPluginIds !== null && (!Array.isArray(effectPluginIds)
      || effectPluginIds.some((pluginId) => !text(pluginId) || text(pluginId).length > 256)
      || new Set(effectPluginIds).size !== effectPluginIds.length)) {
      return malformed("CutAgent CLI returned invalid private Fairlight clip-effect readback.");
    }
    return {
      stableId, nativeId, trackIndex,
      gainDb: optionalNumber(row.gain_db, -160, 60, "clip gain"),
      pan: optionalNumber(row.pan, -100, 100, "clip pan"),
      fadeInFrames: optionalFrames(row.fade_in_frames, "fade-in"),
      fadeOutFrames: optionalFrames(row.fade_out_frames, "fade-out"),
      effectPluginIds: effectPluginIds?.map((pluginId) => text(pluginId)) ?? null,
    };
  });
  const rawTracks = Array.isArray(raw?.tracks) ? raw.tracks : [];
  const tracks = snapshot.fairlight.status === "available"
    ? snapshot.fairlight.tracks.map((row) => {
        const matches = rawTracks.filter((candidate) => integer(candidate?.track_index) === row.trackIndex);
        const rawTrack = matches.length === 1 ? matches[0] : null;
        const channelValues = Array.isArray(rawTrack?.pan_channel_values)
          && rawTrack.pan_channel_values.length === 2
          && rawTrack.pan_channel_values.every((value) => finiteNumber(value) !== null)
          ? rawTrack.pan_channel_values.map((value) => finiteNumber(value))
          : null;
        const neutralStereoPan = rawTrack?.pan_set_supported === false
          && channelValues?.[0] === -100 && channelValues?.[1] === 100;
        return {
          trackIndex: row.trackIndex,
          levelDb: row.levelDb.status === "available" ? row.levelDb.value : null,
          pan: row.pan.status === "available" ? row.pan.value : neutralStereoPan ? 0 : null,
          panWritable: typeof rawTrack?.pan_set_supported === "boolean"
            ? rawTrack.pan_set_supported
            : row.pan.status === "available",
        };
      })
    : [];
  return {status: "available", clips, tracks};
}

function normalizeSnapshot(
  raw,
  before,
  after,
  revisionEvidenceKey,
  privateTimelineItemNativeIdByPublicId = null,
  privateTimelineItemSourcePathByPublicId = null,
) {
  if (!raw || typeof raw !== "object" || !raw.timeline || !Array.isArray(raw.tracks)) {
    return malformed("CutAgent CLI returned malformed timeline snapshot data.");
  }
  const snapshotTimelineName = text(raw.timeline.name);
  const snapshotTimelineNativeId = text(raw.timeline.timeline_id);
  if (!snapshotTimelineName || !snapshotTimelineNativeId) {
    return malformed("CutAgent CLI returned a timeline snapshot without an authoritative identity.");
  }
  if (
    snapshotTimelineName !== before.timeline.name
    || snapshotTimelineName !== after.timeline.name
    || before.project.name !== after.project.name
    || snapshotTimelineNativeId !== before.timelineNativeId
    || snapshotTimelineNativeId !== after.timelineNativeId
  ) {
    throw new SdkLiveInspectionError("STALE_REVISION", "The active timeline changed while CutAgent was reading it.");
  }
  const startFrame = integer(raw.timeline.start_frame);
  if (startFrame === null) return malformed("CutAgent CLI returned an invalid timeline start frame.");
  const rate = frameRate(raw.timeline.fps);
  const trackKeys = new Set();
  const timelineItemIds = new Set();
  let hasUnkeyedTimelineItems = false;
  const normalizedStateTracks = raw.tracks.map((rawTrack) => {
    if (!rawTrack || typeof rawTrack !== "object") return malformed("CutAgent CLI returned a malformed timeline track.");
    const type = text(rawTrack.type);
    if (!new Set(["video", "audio", "subtitle"]).has(type)) return malformed("CutAgent CLI returned an unsupported timeline track type.");
    const index = integer(rawTrack.index);
    if (index === null || index < 1 || index > 4096) return malformed("CutAgent CLI returned an invalid one-based track index.");
    const trackKey = `${type}:${index}`;
    if (trackKeys.has(trackKey)) {
      throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned duplicate timeline track identities.");
    }
    trackKeys.add(trackKey);
    const name = typeof rawTrack.name === "string" ? rawTrack.name : "";
    const rawClips = rawTrack.items;
    if (!Array.isArray(rawClips)) return malformed("CutAgent CLI omitted clip rows from a requested full timeline snapshot.");
    const clips = rawClips.map((rawClip) => {
      if (!rawClip || typeof rawClip !== "object") return malformed("CutAgent CLI returned a malformed timeline clip.");
      const name = text(rawClip.name) || "?";
      const startFrame = integer(rawClip.start);
      const endFrame = integer(rawClip.end);
      const durationFrames = integer(rawClip.duration_frames);
      if (startFrame === null || endFrame === null || durationFrames === null || endFrame <= startFrame || durationFrames !== endFrame - startFrame) {
        return malformed("CutAgent CLI returned invalid clip frame boundaries.");
      }
      const recordSubframes = normalizedRecordSubframes(rawClip, startFrame, endFrame, durationFrames);
      const nativeIdentity = text(rawClip.timeline_item_unique_id);
      if (!nativeIdentity) hasUnkeyedTimelineItems = true;
      const timelineItemId = nativeIdentity
        ? digest("timeline_item_", { timelineId: before.timeline.id, nativeId: nativeIdentity })
        : null;
      if (timelineItemId !== null && timelineItemIds.has(timelineItemId)) {
        throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned an ambiguous native timeline-item identity.");
      }
      if (timelineItemId !== null) timelineItemIds.add(timelineItemId);
      const privateSourcePath = text(rawClip.source_path);
      if (privateSourcePath && privateSourcePath.length > 32_768) {
        return malformed("CutAgent CLI returned an overlong private timeline-item source path.");
      }
      if (timelineItemId !== null && privateTimelineItemSourcePathByPublicId instanceof Map) {
        privateTimelineItemSourcePathByPublicId.set(timelineItemId, privateSourcePath || null);
      }
      // Media Pool references use the canonical GetMediaId-first identity exposed
      // by inventory reads. GetUniqueId may legitimately be a different value.
      const mediaNativeIdentity = text(rawClip.media_pool_item_id);
      const sourceStartFrame = integer(rawClip.source_start_frame);
      const sourceEndFrameExclusive = integer(rawClip.source_end_frame_exclusive);
      const hasSourceStart = rawClip.source_start_frame !== null && rawClip.source_start_frame !== undefined;
      const hasSourceEnd = rawClip.source_end_frame_exclusive !== null && rawClip.source_end_frame_exclusive !== undefined;
      if (hasSourceStart !== hasSourceEnd || (hasSourceStart && (sourceStartFrame === null || sourceEndFrameExclusive === null || sourceEndFrameExclusive <= sourceStartFrame))) {
        return malformed("CutAgent CLI returned malformed or partial source-range evidence.");
      }
      const observedSourceFrameRate = rawClip.source_frame_rate == null || rawClip.source_frame_rate === ""
        ? null
        : frameRate(rawClip.source_frame_rate);
      // Media rate is independent of whether linear clip boundaries are available.
      const sourceFrameRate = observedSourceFrameRate;
      const retimeSource = rawClip.retime_source ?? null;
      if (retimeSource !== null && (
        typeof retimeSource !== "object" || Array.isArray(retimeSource)
        || Object.keys(retimeSource).sort().join(",") !== "availableRange,originFrame"
        || retimeSource.availableRange?.domain !== "source_range" || retimeSource.availableRange?.unit !== "frames"
        || Object.keys(retimeSource.availableRange ?? {}).sort().join(",") !== "domain,endExclusive,start,unit"
        || retimeSource.availableRange.start !== 0 || !Number.isSafeInteger(retimeSource.availableRange.endExclusive)
        || !Number.isFinite(retimeSource.originFrame) || retimeSource.originFrame < 0
        || retimeSource.originFrame >= retimeSource.availableRange.endExclusive || sourceFrameRate === null
      )) return malformed("CutAgent CLI returned invalid retime source authority.");
      const rawLinkedIdentities = rawClip.linked_timeline_item_unique_ids;
      const linkedNativeIdentities = rawLinkedIdentities == null
        ? null
        : Array.isArray(rawLinkedIdentities) && rawLinkedIdentities.every((value) => Boolean(text(value)))
          ? [...new Set(rawLinkedIdentities.map((value) => text(value)))].sort()
          : malformed("CutAgent CLI returned invalid linked timeline-item identities.");
      return {
        value: {
          id: timelineItemId,
          nativeIdentity,
          name,
          recordRange: { domain: "timeline_record_range", unit: "frames", start: startFrame, endExclusive: endFrame },
          duration: { domain: "duration", value: { kind: "frames", value: durationFrames } },
          sourceRange: sourceStartFrame !== null && sourceEndFrameExclusive !== null && sourceEndFrameExclusive > sourceStartFrame
            ? { domain: "source_range", unit: "frames", start: sourceStartFrame, endExclusive: sourceEndFrameExclusive }
            : null,
          sourceFrameRate,
          ...(retimeSource === null ? {} : { retimeSource }),
          mediaPoolItemId: projectSdkMediaPoolItemIdentity(before.project.id, mediaNativeIdentity),
          linkedNativeIdentities,
        },
        revisionEvidence: privateEvidenceDigest(revisionEvidenceKey, {
          source: text(rawClip.source),
          sourcePath: text(rawClip.source_path),
          mediaPoolItemName: text(rawClip.media_pool_item_name),
          retimeTimeMapDigest: text(rawClip.retime_time_map_digest),
          inspectorStateDigest: text(rawClip.inspector_state_digest),
          ...(recordSubframes === null ? {} : {recordSubframes}),
        }),
      };
    });
    return {
      timelineId: before.timeline.id,
      type,
      index,
      name,
      enabled: booleanSymbol(rawTrack.enabled, "enabled"),
      locked: booleanSymbol(rawTrack.locked, "locked"),
      clips: clips.map((clip) => clip.value),
      revisionEvidence: clips.map((clip) => clip.revisionEvidence),
    };
  });
  const publicItemIdByNativeIdentity = new Map();
  for (const track of normalizedStateTracks) {
    for (const clip of track.clips) {
      if (clip.nativeIdentity && clip.id) publicItemIdByNativeIdentity.set(clip.nativeIdentity, clip.id);
    }
  }
  const timelineItemNativeIdByPublicId = privateTimelineItemNativeIdByPublicId instanceof Map
    ? privateTimelineItemNativeIdByPublicId
    : new Map();
  for (const [nativeIdentity, publicItemId] of publicItemIdByNativeIdentity) {
    timelineItemNativeIdByPublicId.set(publicItemId, nativeIdentity);
  }
  for (const track of normalizedStateTracks) {
    for (const clip of track.clips) {
      if (clip.linkedNativeIdentities === null) continue;
      if (clip.nativeIdentity && clip.linkedNativeIdentities.includes(clip.nativeIdentity)) {
        return malformed("DaVinci Resolve returned a timeline item linked to itself.");
      }
      for (const linkedNativeIdentity of clip.linkedNativeIdentities) {
        if (!publicItemIdByNativeIdentity.has(linkedNativeIdentity)) {
          return malformed("DaVinci Resolve returned a linked item outside the complete timeline snapshot.");
        }
      }
    }
  }
  // Resolve can expose a saved link group from only one member immediately
  // after an archive-backed project reopen. A one-sided exact native edge is
  // still authoritative when both endpoints are present in this complete
  // snapshot and both members returned readable link arrays. Close only those
  // observed edges so the public graph represents the native link group
  // symmetrically; null/unreadable topology continues to fail closed below.
  const clipByNativeIdentity = new Map(normalizedStateTracks.flatMap((track) => track.clips
    .filter((clip) => clip.nativeIdentity).map((clip) => [clip.nativeIdentity, clip])));
  for (const track of normalizedStateTracks) {
    for (const clip of track.clips) {
      if (clip.linkedNativeIdentities === null) continue;
      for (const linkedNativeIdentity of clip.linkedNativeIdentities) {
        const linked = clipByNativeIdentity.get(linkedNativeIdentity);
        if (linked?.linkedNativeIdentities !== null && !linked.linkedNativeIdentities.includes(clip.nativeIdentity)) {
          linked.linkedNativeIdentities = [...linked.linkedNativeIdentities, clip.nativeIdentity].sort();
        }
      }
    }
  }
  const normalizedFairlight = normalizeFairlightReadback(raw.fairlight);
  const privateFairlightPlanReadback = normalizePrivateFairlightPlanReadback(
    raw.fairlight,
    timelineItemNativeIdByPublicId,
    {fairlight: normalizedFairlight},
  );
  const publicFairlight = normalizedFairlight.status === "available"
    ? {
        ...normalizedFairlight,
        clips: privateFairlightPlanReadback.status === "available"
          ? privateFairlightPlanReadback.clips.map(({nativeId: _nativeId, stableId, trackIndex, gainDb, pan, fadeInFrames, fadeOutFrames}) => {
              const observed = (value) => value === null
                ? {status: "unavailable", reason: "readback_unavailable"}
                : {status: "available", value};
              return {
                clipId: stableId,
                trackIndex,
                gainDb: observed(gainDb),
                pan: observed(pan === null ? null : pan / 100),
                fadeInFrames: observed(fadeInFrames),
                fadeOutFrames: observed(fadeOutFrames),
              };
            })
          : [],
      }
    : normalizedFairlight;
  if (!Array.isArray(raw.markers)) return malformed("CutAgent CLI omitted marker rows from the full timeline snapshot.");
  const markerFrames = new Set();
  const normalizedStateMarkers = raw.markers.map((rawMarker) => {
    if (!rawMarker || typeof rawMarker !== "object") return malformed("CutAgent CLI returned a malformed timeline marker.");
    const recordFrame = integer(rawMarker.record_frame);
    const durationFrames = integer(rawMarker.duration);
    const color = text(rawMarker.color);
    const customData = rawMarker.custom_data;
    if (recordFrame === null || recordFrame < 0 || durationFrames === null || durationFrames < 1 || !color) {
      return malformed("CutAgent CLI returned invalid timeline marker values.");
    }
    if (typeof customData !== "string" || customData.length > 65_536) {
      return malformed("CutAgent CLI returned invalid private marker custom data.");
    }
    if (markerFrames.has(recordFrame)) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned duplicate markers at one record frame.");
    markerFrames.add(recordFrame);
    const value = {
      position: { domain: "timeline_record", value: { kind: "frames", value: recordFrame } },
      color,
      name: typeof rawMarker.name === "string" ? rawMarker.name : "",
      note: typeof rawMarker.note === "string" ? rawMarker.note : "",
      duration: { domain: "duration", value: { kind: "frames", value: durationFrames } },
    };
    return {
      id: digest("marker_", { projectId: before.project.id, timelineId: before.timeline.id, ...value }),
      ...value,
      customDataEvidence: privateEvidenceDigest(revisionEvidenceKey, customData),
    };
  });
  const revision = digest("revision_", {
    project: before.project,
    timeline: before.timeline,
    frameRate: rate,
    start: { domain: "timeline_record", value: { kind: "frames", value: startFrame } },
    tracks: normalizedStateTracks.map((track) => ({
      timelineId: track.timelineId,
      type: track.type,
      index: track.index,
      name: track.name,
      enabled: track.enabled,
      locked: track.locked,
      clips: track.clips,
      revisionEvidence: track.revisionEvidence,
    })),
    markers: normalizedStateMarkers,
    fairlight: publicFairlight,
    privateFairlightPlanEvidence: privateEvidenceDigest(revisionEvidenceKey, raw.fairlight?.plan_readback ?? null),
  });
  const snapshotObservation = hasUnkeyedTimelineItems
    ? crypto.randomBytes(16).toString("base64url")
    : revision;
  const normalizedTracks = normalizedStateTracks.map((track) => {
    const snapshotId = digest("snapshot_track_", {
      revision,
      snapshotObservation,
      timelineId: before.timeline.id,
      type: track.type,
      index: track.index,
    });
    return {
      timelineId: track.timelineId,
      type: track.type,
      index: track.index,
      name: track.name,
      enabled: track.enabled,
      locked: track.locked,
      snapshotId,
      clips: track.clips.map((clip, clipOffset) => {
        const { nativeIdentity: _nativeIdentity, linkedNativeIdentities, ...publicClip } = clip;
        return {
          ...publicClip,
          linkedItemIds: linkedNativeIdentities === null
            ? null
            : linkedNativeIdentities.map((linkedNativeIdentity) => publicItemIdByNativeIdentity.get(linkedNativeIdentity)),
          snapshotId: digest("snapshot_timeline_item_", { revision, snapshotObservation, snapshotTrackId: snapshotId, ordinal: clipOffset }),
          snapshotTrackId: snapshotId,
        };
      }),
    };
  });
  return parseRuntime(sdkTimelineSnapshotSchema, {
    project: before.project,
    timeline: before.timeline,
    revision,
    frameRate: rate,
    start: { domain: "timeline_record", value: { kind: "frames", value: startFrame } },
    tracks: normalizedTracks.map((track) => ({
      ...track,
      snapshotRevision: revision,
      clips: track.clips.map((clip) => ({ ...clip, snapshotRevision: revision })),
    })),
    markers: normalizedStateMarkers.map(({ customDataEvidence: _customDataEvidence, ...marker }) => ({ ...marker, snapshotRevision: revision })),
    fairlight: publicFairlight,
  }, "CutAgent CLI returned a timeline snapshot that violated the SDK contract.");
}

function exactRetimeTarget(snapshot, expected) {
  if (!expected || typeof expected !== "object" || expected.snapshotRevision !== snapshot.revision) return null;
  const matches = snapshot.tracks.flatMap((track) => track.clips
    .filter((clip) => {
      const sourceAuthority = clip.sourceRange ?? clip.retimeSource?.availableRange;
      return (
      clip.id === expected.id
      && clip.snapshotId === expected.snapshotId
      && clip.snapshotTrackId === expected.snapshotTrackId
      && clip.snapshotRevision === expected.snapshotRevision
      && track.type === expected.trackType
      && track.index === expected.trackIndex
      && clip.name === expected.name
      && clip.recordRange.start === expected.recordRange?.start
      && clip.recordRange.endExclusive === expected.recordRange?.endExclusive
      && clip.duration.value.value === expected.duration?.value?.value
      && sourceAuthority?.start === expected.sourceRange?.start
      && sourceAuthority?.endExclusive === expected.sourceRange?.endExclusive
      && JSON.stringify(clip.sourceFrameRate) === JSON.stringify(expected.sourceFrameRate)
      && clip.mediaPoolItemId === expected.mediaPoolItemId
      && JSON.stringify(clip.linkedItemIds) === JSON.stringify(expected.linkedItemIds)
      );
    })
    .map((clip) => ({ track, clip })));
  return matches.length === 1 ? matches[0] : null;
}

function normalizeRetimeState(raw, timelineItemId) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.points)) {
    return malformed("CutAgent CLI omitted decoded retime state.");
  }
  const finite = (value) => typeof value === "number" && Number.isFinite(value) ? value : null;
  const points = raw.points.map((point) => {
    const recordFrame = strictInteger(point?.record_frame);
    const recordPositionFrames = finite(point?.record_position);
    const sourceFrame = finite(point?.source_frame);
    const recordFrameIn = finite(point?.record_frame_in);
    const sourceFrameIn = finite(point?.source_frame_in);
    const recordFrameOut = finite(point?.record_frame_out);
    const sourceFrameOut = finite(point?.source_frame_out);
    const speed = finite(point?.speed);
    if (recordFrame === null || recordPositionFrames === null || sourceFrame === null
      || recordFrameIn === null || sourceFrameIn === null || recordFrameOut === null
      || sourceFrameOut === null || speed === null) {
      return malformed("CutAgent CLI returned an incomplete decoded retime point.");
    }
    return {
      recordFrame,
      recordPositionFrames,
      sourceFrame,
      incomingControl: { recordPositionFrames: recordFrameIn, sourceFrame: sourceFrameIn },
      outgoingControl: { recordPositionFrames: recordFrameOut, sourceFrame: sourceFrameOut },
      speed,
      interpolation: point.interpolation,
    };
  });
  return {
    timelineItemId,
    durationFrames: raw.duration_frames,
    speedMultiplier: raw.speed_multiplier,
    reversed: raw.reversed,
    frozen: raw.frozen,
    points,
  };
}

function isDefaultManagedRetime(state) {
  if (!state || state.speedMultiplier !== 1 || state.reversed !== false || state.frozen !== false
    || !Array.isArray(state.points) || state.points.length !== 2) return false;
  const close = (left, right) => Number.isFinite(left) && Number.isFinite(right) && Math.abs(left - right) < 1e-9;
  if (state.points.some((point) => point.interpolation !== "linear" || !close(point.speed, 1)
    || !close(point.incomingControl.recordPositionFrames, point.recordPositionFrames)
    || !close(point.incomingControl.sourceFrame, point.sourceFrame)
    || !close(point.outgoingControl.recordPositionFrames, point.recordPositionFrames)
    || !close(point.outgoingControl.sourceFrame, point.sourceFrame))) return false;
  const [first, last] = state.points;
  return close(last.sourceFrame - first.sourceFrame, last.recordPositionFrames - first.recordPositionFrames);
}

function coordinate(value, label) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 257) {
    return malformed(`CutAgent CLI returned an invalid Media Pool ${label} coordinate.`);
  }
  const normalized = value.map(strictInteger);
  if (normalized.some((part) => part === null || part < 0 || part > 1_000_000)) {
    return malformed(`CutAgent CLI returned an invalid Media Pool ${label} coordinate.`);
  }
  return normalized;
}

function mediaPoolNullableText(value, maximum = 4096) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value !== "string" || value.length > maximum) return malformed("CutAgent CLI returned malformed Media Pool text data.");
  return value;
}

function mediaPoolName(value) {
  if (typeof value !== "string" || !value.trim() || value.length > 4096) {
    return malformed("CutAgent CLI returned a malformed Media Pool name.");
  }
  return value;
}

function sourceFileName(value) {
  const normalized = mediaPoolNullableText(value);
  if (normalized !== null && (normalized === "." || normalized === ".." || normalized.includes("/") || normalized.includes("\\"))) {
    return malformed("CutAgent CLI returned a path instead of a Media Pool source basename.");
  }
  return normalized;
}

function normalizeMediaPoolPage(raw, project, request) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.entries)) {
    return malformed("CutAgent CLI returned malformed Media Pool page data.");
  }
  const poolDigest = text(raw.pool_digest);
  if (!/^[a-f0-9]{64}$/.test(poolDigest)) return malformed("CutAgent CLI omitted the Media Pool content digest.");
  if (raw.ambiguous_native_ids === true) {
    throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned duplicate authoritative Media Pool identities.");
  }
  if (raw.ambiguous_native_ids !== false) return malformed("CutAgent CLI omitted Media Pool identity ambiguity evidence.");
  const offset = strictInteger(raw.offset);
  const pageSize = strictInteger(raw.page_size);
  const total = strictInteger(raw.total);
  const nextOffset = raw.next_offset === null ? null : strictInteger(raw.next_offset);
  if (offset === null || pageSize === null || total === null || (raw.next_offset !== null && nextOffset === null)) {
    return malformed("CutAgent CLI returned invalid Media Pool pagination data.");
  }
  if (offset !== request.offset || pageSize !== request.pageSize) {
    return malformed("CutAgent CLI returned a Media Pool page for different request coordinates.");
  }
  if (JSON.stringify(canonicalize(raw.search)) !== JSON.stringify(canonicalize(request.search))) {
    return malformed("CutAgent CLI returned a Media Pool page for a different search.");
  }
  const revision = digest("revision_", { projectId: project.id, poolDigest });
  const currentFolderNativeId = raw.current_folder_native_id == null ? null : text(raw.current_folder_native_id);
  if (raw.current_folder_native_id != null && !currentFolderNativeId) {
    return malformed("CutAgent CLI returned malformed current Media Pool folder identity.");
  }
  const currentFolderId = currentFolderNativeId
    ? projectSdkMediaPoolFolderIdentity(project.id, currentFolderNativeId)
    : null;
  if (request.expectedRevision !== null && request.expectedRevision !== revision) {
    throw new SdkLiveInspectionError("STALE_REVISION", "The Media Pool changed between bounded page reads.");
  }
  const folders = [];
  const assets = [];
  const privateEntries = [];
  const durableFolderIds = new Set();
  const durableAssetIds = new Set();
  for (const entry of raw.entries) {
    if (!entry || typeof entry !== "object") return malformed("CutAgent CLI returned a malformed Media Pool entry.");
    if (entry.entry_kind === "folder") {
      const ownCoordinate = coordinate(entry.coordinate, "folder");
      const parentCoordinate = entry.parent_coordinate === null ? null : coordinate(entry.parent_coordinate, "parent folder");
      const nativeId = text(entry.native_id);
      const id = nativeId ? projectSdkMediaPoolFolderIdentity(project.id, nativeId) : null;
      if (id && durableFolderIds.has(id)) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned duplicate Media Pool folder identities.");
      if (id) durableFolderIds.add(id);
      const depth = strictInteger(entry.depth);
      if (depth === null) return malformed("CutAgent CLI returned an invalid Media Pool folder depth.");
      const folderName = mediaPoolName(entry.name);
      folders.push({
        id,
        snapshotId: digest("snapshot_media_pool_folder_", { revision, coordinate: ownCoordinate }),
        parentSnapshotId: parentCoordinate === null
          ? null
          : digest("snapshot_media_pool_folder_", { revision, coordinate: parentCoordinate }),
        snapshotRevision: revision,
        name: folderName,
        depth,
      });
      privateEntries.push({
        entryKind: "folder",
        id,
        nativeId: nativeId || null,
        coordinate: ownCoordinate,
        parentCoordinate,
        name: folderName,
        depth,
      });
      continue;
    }
    if (entry.entry_kind !== "asset") return malformed("CutAgent CLI returned an unknown Media Pool entry kind.");
    const ownCoordinate = coordinate(entry.coordinate, "asset");
    const folderCoordinate = coordinate(entry.folder_coordinate, "asset folder");
    const nativeId = text(entry.native_id);
    const uniqueId = entry.unique_id == null ? null : text(entry.unique_id);
    if (entry.unique_id != null && !uniqueId) return malformed("CutAgent CLI returned malformed Media Pool unique identity.");
    const id = nativeId ? digest("media_pool_item_", { projectId: project.id, nativeId }) : null;
    if (id && durableAssetIds.has(id)) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned duplicate Media Pool asset identities.");
    if (id) durableAssetIds.add(id);
    if (!Array.isArray(entry.metadata)) return malformed("CutAgent CLI returned malformed Media Pool metadata.");
    const assetName = mediaPoolName(entry.name);
    const assetSourceFileName = sourceFileName(entry.source_file_name);
    const sourcePath = mediaPoolNullableText(entry.source_path, 32_768);
    if (sourcePath !== null && assetSourceFileName !== sourcePath.replaceAll("\\", "/").split("/").at(-1)) {
      return malformed("CutAgent CLI returned inconsistent private Media Pool source-path evidence.");
    }
    const asset = {
      id,
      snapshotId: digest("snapshot_media_pool_item_", { revision, coordinate: ownCoordinate }),
      folderSnapshotId: digest("snapshot_media_pool_folder_", { revision, coordinate: folderCoordinate }),
      snapshotRevision: revision,
      name: assetName,
      kind: entry.kind,
      selected: entry.selected,
      sourceFileName: assetSourceFileName,
      duration: mediaPoolNullableText(entry.duration),
      resolution: mediaPoolNullableText(entry.resolution),
      frameRate: mediaPoolNullableText(entry.frame_rate, 256),
      startTimecode: mediaPoolNullableText(entry.start_timecode, 256),
      metadata: entry.metadata,
    };
    assets.push(asset);
    privateEntries.push({
      entryKind: "asset",
      id,
      nativeId: text(entry.native_id),
      uniqueId,
      folderCoordinate,
      name: assetName,
      kind: asset.kind,
      selected: asset.selected,
      sourcePath,
      sourceFileName: assetSourceFileName,
      duration: asset.duration,
      resolution: asset.resolution,
      frameRate: asset.frameRate,
      startTimecode: asset.startTimecode,
      metadata: asset.metadata,
    });
  }
  const value = parseRuntime(sdkMediaPoolPageSchema, {
    project,
    revision,
    offset,
    pageSize,
    total,
    nextOffset,
    search: request.search,
    folders,
    assets,
  }, "CutAgent CLI returned a Media Pool page that violated the SDK contract.");
  return {
    value,
    privateMediaPoolState: { poolDigest, entries: privateEntries, currentFolderId },
  };
}

function colorCapability(value) {
  if (value?.status === "supported") return { status: "supported" };
  if (value?.status === "unavailable" && value?.reason === "not_exposed_by_runtime") {
    return { status: "unavailable", reason: "not_exposed_by_runtime" };
  }
  return malformed("CutAgent CLI returned malformed Color capability evidence.");
}

function publicLut(rawValue) {
  if (rawValue !== null && rawValue !== undefined && typeof rawValue !== "string") {
    return malformed("CutAgent CLI returned malformed Color LUT metadata.");
  }
  const value = text(rawValue);
  if (!value) return { applied: false, displayName: null };
  const displayName = value.replace(/\\/g, "/").split("/").filter(Boolean).pop() || null;
  if (!displayName || displayName.length > 1024) {
    return malformed("CutAgent CLI returned invalid Color LUT metadata.");
  }
  return { applied: true, displayName };
}

function publicEffect(rawValue) {
  if (typeof rawValue !== "string") {
    return malformed("CutAgent CLI returned malformed Color effect metadata.");
  }
  if (rawValue.length > 512 || /\p{C}/u.test(rawValue)) {
    return malformed("CutAgent CLI returned invalid Color effect metadata.");
  }
  const value = rawValue.trim();
  const normalized = value.replace(/\\/g, "/");
  const pathLike = /^(?:[\\/]|file:|[A-Za-z]:)/i.test(value)
    || normalized.startsWith("~")
    || (normalized.includes("/") && value !== "ARRI CDL/LUT");
  if (!value || pathLike) {
    return malformed("CutAgent CLI returned invalid Color effect metadata.");
  }
  return value;
}

function timelineEditTrack(snapshot, type, index) {
  const matches = snapshot.tracks.filter((track) => track.type === type && track.index === index);
  if (matches.length === 0) throw new SdkLiveInspectionError("TARGET_NOT_FOUND", `The requested ${type} track was not found.`);
  if (matches.length !== 1) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", `The requested ${type} track is ambiguous.`);
  return matches[0];
}

function editTrackTarget(track) {
  return { type: track.type, index: track.index, snapshotId: track.snapshotId };
}

function editItemTarget(clip, track, role) {
  if (!clip.id) throw new SdkLiveInspectionError("INVALID_RESPONSE", "Timeline edit impact requires authoritative identities for every affected or protected item.");
  return { id: clip.id, track: editTrackTarget(track), recordRange: clip.recordRange, role };
}

function finalizeTimelineEditImpact(candidate) {
  const parsed = sdkTimelineEditImpactSchema.parse({ ...candidate, impactId: digest("impact_", candidate) });
  const { impactId: _provisionalImpactId, ...normalized } = parsed;
  return sdkTimelineEditImpactSchema.parse({ ...normalized, impactId: digest("impact_", normalized) });
}

function overlaps(left, right) {
  return left.start < right.endExclusive && right.start < left.endExclusive;
}

function buildTimelineEditImpact(intent, snapshot, rawPlan) {
  if (snapshot.revision !== intent.timelineRevision) throw new SdkLiveInspectionError("STALE_REVISION", "The timeline changed before the edit impact could be resolved.");
  if (intent.action === "remove") {
    const rows = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
    const matches = rows.filter(({ track, clip }) => clip.id === intent.clipId
      && clip.name === intent.clipName
      && track.type === intent.trackType
      && track.index === intent.trackIndex
      && clip.recordRange.start === intent.currentRecordRange.start
      && clip.recordRange.endExclusive === intent.currentRecordRange.endExclusive);
    if (matches.length === 0) throw new SdkLiveInspectionError("STALE_REVISION", "The exact remove target changed or disappeared after inspection.");
    if (matches.length !== 1) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "The exact remove target is ambiguous.");
    const { track, clip } = matches[0];
    if (clip.linkedItemIds === null) throw new SdkLiveInspectionError("INVALID_RESPONSE", "DaVinci Resolve could not prove the remove target's linked-item topology.");
    const transitions = clip.linkedItemIds.map((linkedId) => {
      const linked = rows.find((row) => row.clip.id === linkedId);
      if (!linked || linked.clip.linkedItemIds === null || !linked.clip.linkedItemIds.includes(clip.id)) {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "Remove requires complete reciprocal linked-item topology.");
      }
      return { itemId: linkedId, beforeLinkedItemIds: linked.clip.linkedItemIds, afterLinkedItemIds: linked.clip.linkedItemIds.filter((id) => id !== clip.id) };
    });
    const transitionIds = new Set(transitions.map((transition) => transition.itemId));
    const protectedItems = rows.filter((row) => row.clip.id !== clip.id && !transitionIds.has(row.clip.id))
      .map(({ track: candidateTrack, clip: candidateClip }) => editItemTarget(candidateClip, candidateTrack, "protected_neighbor"));
    const candidate = {
      action: "remove", projectId: intent.projectId, timelineId: intent.timelineId, timelineRevision: intent.timelineRevision, intent,
      recordRange: clip.recordRange, affectedTracks: [editTrackTarget(track)], affectedItems: [editItemTarget(clip, track, "remove")],
      protectedItems, expectedItems: [], expectedLinkTransitions: transitions,
      linkedAudio: { behavior: "exclude", topologyProven: true }, capabilityId: "timeline.items_delete",
      summary: `Remove one exact ${track.type} timeline item while preserving ${protectedItems.length} resolved targets.`,
    };
    return finalizeTimelineEditImpact(candidate);
  }
  const plan = rawPlan?.payload ?? rawPlan;
  if (!plan || typeof plan !== "object" || plan.action !== `edit.${intent.action}`) {
    throw new SdkLiveInspectionError("INVALID_RESPONSE", "CutAgent CLI returned the wrong semantic edit preview.");
  }
  let recordRange;
  const affectedTracks = [];
  const affectedItems = [];
  const protectedItems = [];
  const expectedItems = [];
  let topologyProven = true;
  if (intent.action === "insert" || intent.action === "overwrite") {
    const placementType = intent.placement ?? "video";
    const placement = plan.placement;
    if (!placement || !Number.isSafeInteger(placement.record_start_frame) || !Number.isSafeInteger(placement.record_end_frame_exclusive)
      || placement.record_start_frame !== intent.at.value.value || placement.record_end_frame_exclusive <= placement.record_start_frame) {
      throw new SdkLiveInspectionError("INVALID_RESPONSE", "CutAgent CLI returned invalid edit placement impact.");
    }
    recordRange = { domain: "timeline_record_range", unit: "frames", start: placement.record_start_frame, endExclusive: placement.record_end_frame_exclusive };
    const tracks = [];
    const resolvedAudioTrack = plan.target?.audio_track_index;
    const linkedAudioResolved = plan.effects?.linked_audio;
    if (placementType === "audio") {
      if (plan.target?.video_track_index !== null || resolvedAudioTrack !== intent.audioTrackIndex || linkedAudioResolved !== false) {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "CutAgent CLI did not resolve the exact requested audio-only track.");
      }
      tracks.push(timelineEditTrack(snapshot, "audio", resolvedAudioTrack));
    } else {
      const videoTrack = timelineEditTrack(snapshot, "video", intent.videoTrackIndex);
      tracks.push(videoTrack);
    }
    if (placementType === "video" && intent.linkedAudio === "include") {
      if (intent.audioTrackIndex === null || resolvedAudioTrack !== intent.audioTrackIndex || linkedAudioResolved !== true) {
        throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The selected source did not resolve linked audio on the exact requested audio track.");
      }
      tracks.push(timelineEditTrack(snapshot, "audio", resolvedAudioTrack));
    } else if (placementType === "video" && (resolvedAudioTrack !== null || linkedAudioResolved !== false)) {
      throw new SdkLiveInspectionError("INVALID_RESPONSE", "CutAgent CLI did not honor the requested video-only placement semantics.");
    }
    const sourceStart = plan.source?.range?.start_frame;
    const sourceEnd = plan.source?.range?.end_frame_exclusive;
    const replacementSourceEndTolerance = plan.source?.range?.source_end_tolerance_frames;
    if (!Number.isSafeInteger(sourceStart) || !Number.isSafeInteger(sourceEnd) || sourceEnd <= sourceStart
      || !Number.isSafeInteger(replacementSourceEndTolerance) || replacementSourceEndTolerance < 1 || replacementSourceEndTolerance > 4096) {
      throw new SdkLiveInspectionError("INVALID_RESPONSE", "CutAgent CLI returned an invalid placement source range.");
    }
    affectedTracks.push(...tracks.map(editTrackTarget));
    for (const track of tracks) {
      const overlapping = track.clips.filter((clip) => overlaps(clip.recordRange, recordRange));
      if (intent.action === "insert" && overlapping.length > 0) {
        throw new SdkLiveInspectionError("INVALID_REQUEST", "A non-ripple insert requires an unoccupied range on every target track. Choose a free range or preview an overwrite.");
      }
      if (intent.action === "overwrite") affectedItems.push(...overlapping.map((clip) => editItemTarget(clip, track, "replace")));
      topologyProven = topologyProven && overlapping.every((clip) => clip.linkedItemIds !== null);
      const before = track.clips.filter((clip) => clip.recordRange.endExclusive <= recordRange.start).at(-1);
      const after = track.clips.find((clip) => clip.recordRange.start >= recordRange.endExclusive);
      if (before) protectedItems.push(editItemTarget(before, track, "protected_neighbor"));
      if (after) protectedItems.push(editItemTarget(after, track, "protected_neighbor"));
      expectedItems.push({
        role: "replacement", beforeItemId: null, track: editTrackTarget(track), recordRange,
        sourceRange: { domain: "source_range", unit: "frames", start: sourceStart, endExclusive: sourceEnd },
        sourceEndToleranceFrames: replacementSourceEndTolerance,
        mediaPoolItemId: intent.source.id,
        name: intent.source.name,
      });
    }
    if (intent.action === "overwrite") {
      if (!topologyProven) {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "DaVinci Resolve could not prove every overwritten target's linked-media topology.");
      }
      const affectedIds = new Set(affectedItems.map((item) => item.id));
      const affectedTrackCoordinates = new Set(affectedTracks.map((track) => `${track.type}:${track.index}`));
      const snapshotRows = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({ track, clip })));
      for (const item of affectedItems) {
        const row = snapshotRows.find((candidate) => candidate.clip.id === item.id);
        if (!row || row.clip.linkedItemIds === null) {
          throw new SdkLiveInspectionError("INVALID_RESPONSE", "An overwritten target lacked authoritative linked-media topology.");
        }
        if (intent.linkedAudio === "exclude" && row.clip.linkedItemIds.length > 0) {
          throw new SdkLiveInspectionError("INVALID_RESPONSE", "Video-only overwrite cannot safely target an item linked to mutable audio.");
        }
        if (intent.linkedAudio === "include") {
          for (const linkedId of row.clip.linkedItemIds) {
            const linked = snapshotRows.find((candidate) => candidate.clip.id === linkedId);
            const linkedTrack = linked ? `${linked.track.type}:${linked.track.index}` : null;
            if (!linked || linked.clip.linkedItemIds === null || !linked.clip.linkedItemIds.includes(item.id)
              || !affectedIds.has(linkedId) || !affectedTrackCoordinates.has(linkedTrack)) {
              throw new SdkLiveInspectionError("INVALID_RESPONSE", "Linked overwrite topology escaped the exact affected tracks or impact model.");
            }
          }
        }
      }
    }
    for (const segment of plan.effects?.preserved_edge_segments ?? []) {
      const segmentTrack = timelineEditTrack(snapshot, segment.track_type, segment.track_index);
      const mediaPoolItemId = typeof segment.media_id === "string" && segment.media_id
        ? digest("media_pool_item_", { projectId: intent.projectId, nativeId: segment.media_id }) : null;
      const segmentRange = { start: segment.record_start_frame, endExclusive: segment.record_end_frame_exclusive };
      const segmentSourceEndTolerance = segment.source_end_tolerance_frames;
      const originals = segmentTrack.clips.filter((clip) => clip.mediaPoolItemId === mediaPoolItemId
        && clip.recordRange.start <= segmentRange.start && clip.recordRange.endExclusive >= segmentRange.endExclusive);
      if (originals.length !== 1 || !mediaPoolItemId || !Number.isSafeInteger(segmentRange.start) || !Number.isSafeInteger(segmentRange.endExclusive)
        || !Number.isSafeInteger(segment.source_start_frame) || !Number.isSafeInteger(segment.source_end_frame_exclusive)
        || !Number.isSafeInteger(segmentSourceEndTolerance) || segmentSourceEndTolerance < 1 || segmentSourceEndTolerance > 4096
        || !["head", "tail"].includes(segment.side)) {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "CutAgent CLI returned an incomplete or ambiguous preserved-edge plan.");
      }
      expectedItems.push({
        role: "preserved_edge", beforeItemId: originals[0].id, track: editTrackTarget(segmentTrack),
        recordRange: { domain: "timeline_record_range", unit: "frames", ...segmentRange },
        sourceRange: { domain: "source_range", unit: "frames", start: segment.source_start_frame, endExclusive: segment.source_end_frame_exclusive },
        sourceEndToleranceFrames: segmentSourceEndTolerance,
        mediaPoolItemId,
        name: originals[0].name,
        preservedEdgeSide: segment.side,
      });
    }
  } else {
    if (plan.linked_audio_mode !== intent.linkedAudio
      || plan.head_trimmed_frames !== intent.headFrames
      || plan.tail_trimmed_frames !== intent.tailFrames) {
      throw new SdkLiveInspectionError("INVALID_RESPONSE", "CutAgent CLI did not preserve the exact requested trim semantics.");
    }
    const track = timelineEditTrack(snapshot, "video", intent.trackIndex);
    const matches = track.clips.filter((clip) => clip.id === intent.clipId && clip.recordRange.start === intent.currentRecordRange.start && clip.recordRange.endExclusive === intent.currentRecordRange.endExclusive);
    if (matches.length === 0) throw new SdkLiveInspectionError("STALE_REVISION", "The trim target changed or disappeared after inspection.");
    if (matches.length !== 1) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "The trim target is ambiguous.");
    const clip = matches[0];
    if (!clip.sourceRange || !clip.mediaPoolItemId) throw new SdkLiveInspectionError("INVALID_RESPONSE", "The trim target requires an authoritative source range and Media Pool identity.");
    if (!clip.sourceFrameRate) throw new SdkLiveInspectionError("INVALID_RESPONSE", "The trim target requires an authoritative source frame rate.");
    if (clip.linkedItemIds === null) throw new SdkLiveInspectionError("INVALID_RESPONSE", "DaVinci Resolve could not prove the trim target's linked-media topology.");
    recordRange = {
      domain: "timeline_record_range",
      unit: "frames",
      start: clip.recordRange.start + intent.headFrames,
      endExclusive: clip.recordRange.endExclusive - intent.tailFrames,
    };
    const planTargets = Array.isArray(plan.targets) ? plan.targets : [];
    const exactPlanTarget = (candidateTrack, candidateClip, expectedRecordRange) => {
      const candidates = planTargets.filter((target) => target.track_type === candidateTrack.type
        && target.track_index === candidateTrack.index
        && target.name === candidateClip.name
        && target.old_start === candidateClip.recordRange.start
        && target.old_end === candidateClip.recordRange.endExclusive);
      if (candidates.length !== 1) {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "CutAgent CLI did not return one exact trim source plan for the target.");
      }
      const target = candidates[0];
      const sourceRate = Number(candidateClip.sourceFrameRate.numerator) / Number(candidateClip.sourceFrameRate.denominator);
      if (!Number.isFinite(target.source_frame_rate) || Math.abs(target.source_frame_rate - sourceRate) > 0.001
        || target.old_source_start_frame !== candidateClip.sourceRange.start
        || target.old_source_end_frame_exclusive !== candidateClip.sourceRange.endExclusive
        || target.new_start !== expectedRecordRange.start
        || target.new_end !== expectedRecordRange.endExclusive
        || !Number.isSafeInteger(target.new_source_start_frame)
        || !Number.isSafeInteger(target.new_source_end_frame_exclusive)
        || target.new_source_end_frame_exclusive <= target.new_source_start_frame) {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "CutAgent CLI returned an inconsistent trim source plan.");
      }
      return target;
    };
    const videoPlan = exactPlanTarget(track, clip, recordRange);
    const timelineRate = snapshot.frameRate.numerator / snapshot.frameRate.denominator;
    const videoSourceRate = clip.sourceFrameRate.numerator / clip.sourceFrameRate.denominator;
    const videoSourceEndTolerance = Math.abs(videoSourceRate - timelineRate) <= 0.000001
      ? 0
      : Math.max(1, Math.ceil(videoSourceRate / timelineRate));
    affectedTracks.push(editTrackTarget(track));
    affectedItems.push(editItemTarget(clip, track, "trim"));
    expectedItems.push({
      role: "trimmed", beforeItemId: clip.id, track: editTrackTarget(track), recordRange,
      sourceRange: { domain: "source_range", unit: "frames", start: videoPlan.new_source_start_frame, endExclusive: videoPlan.new_source_end_frame_exclusive },
      sourceEndToleranceFrames: videoSourceEndTolerance,
      mediaPoolItemId: clip.mediaPoolItemId,
      name: clip.name,
    });
    const trimRows = [{ candidateTrack: track, candidateClip: clip }];
    for (const linkedId of clip.linkedItemIds) {
      const linked = snapshot.tracks.flatMap((candidateTrack) => candidateTrack.clips.map((candidateClip) => ({ candidateTrack, candidateClip })))
        .find(({ candidateClip }) => candidateClip.id === linkedId);
      if (!linked) throw new SdkLiveInspectionError("INVALID_RESPONSE", "A linked trim target was absent from the complete snapshot.");
      if (!linked.candidateClip.sourceRange || !linked.candidateClip.mediaPoolItemId || linked.candidateClip.linkedItemIds === null) {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "The linked trim item lacks authoritative source, media, or topology evidence.");
      }
      if (!linked.candidateClip.linkedItemIds.includes(clip.id)) {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "Linked trim requires exact reciprocal video/audio topology.");
      }
      if (intent.linkedAudio === "exclude") {
        continue;
      } else {
        if (!linked.candidateClip.sourceFrameRate) {
          throw new SdkLiveInspectionError("INVALID_RESPONSE", "The linked trim target requires an authoritative source frame rate.");
        }
        if (linked.candidateTrack.type !== "audio"
          || linked.candidateClip.recordRange.start !== clip.recordRange.start
          || linked.candidateClip.recordRange.endExclusive !== clip.recordRange.endExclusive) {
          throw new SdkLiveInspectionError("INVALID_RESPONSE", "Linked trim requires synchronized audio with the exact video record range.");
        }
        affectedTracks.push(editTrackTarget(linked.candidateTrack));
        affectedItems.push(editItemTarget(linked.candidateClip, linked.candidateTrack, "linked"));
        const linkedPlan = exactPlanTarget(linked.candidateTrack, linked.candidateClip, recordRange);
        const linkedSourceRate = linked.candidateClip.sourceFrameRate.numerator
          / linked.candidateClip.sourceFrameRate.denominator;
        const linkedSourceEndTolerance = Math.abs(linkedSourceRate - timelineRate) <= 0.000001
          ? 0
          : Math.max(1, Math.ceil(linkedSourceRate / timelineRate));
        expectedItems.push({
          role: "trimmed", beforeItemId: linked.candidateClip.id, track: editTrackTarget(linked.candidateTrack), recordRange,
          sourceRange: { domain: "source_range", unit: "frames", start: linkedPlan.new_source_start_frame, endExclusive: linkedPlan.new_source_end_frame_exclusive },
          sourceEndToleranceFrames: linkedSourceEndTolerance,
          mediaPoolItemId: linked.candidateClip.mediaPoolItemId,
          name: linked.candidateClip.name,
        });
        trimRows.push(linked);
      }
    }
    if (planTargets.length !== trimRows.length) {
      throw new SdkLiveInspectionError("INVALID_RESPONSE", "CutAgent CLI returned an unexpected trim source-plan target set.");
    }
    if (intent.linkedAudio === "preserve") {
      const planMatches = trimRows.every(({ candidateTrack, candidateClip }) => planTargets.some((target) => target.track_type === candidateTrack.type
        && target.track_index === candidateTrack.index
        && target.name === candidateClip.name
        && target.old_start === candidateClip.recordRange.start
        && target.old_end === candidateClip.recordRange.endExclusive
        && target.new_start === recordRange.start
        && target.new_end === recordRange.endExclusive));
      if (!planMatches) {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "CutAgent CLI did not resolve the complete linked video/audio trim target set.");
      }
    }
    const before = track.clips.filter((candidate) => candidate.id !== clip.id && candidate.recordRange.endExclusive <= clip.recordRange.start).at(-1);
    const after = track.clips.find((candidate) => candidate.id !== clip.id && candidate.recordRange.start >= clip.recordRange.endExclusive);
    if (before) protectedItems.push(editItemTarget(before, track, "protected_neighbor"));
    if (after) protectedItems.push(editItemTarget(after, track, "protected_neighbor"));
  }
  for (const track of snapshot.tracks.filter((candidate) => candidate.type === "subtitle")) {
    for (const clip of track.clips.filter((candidate) => overlaps(candidate.recordRange, recordRange))) {
      protectedItems.push(editItemTarget(clip, track, "protected_overlap"));
    }
  }
  const affectedIds = new Set(affectedItems.map((item) => item.id));
  const alreadyProtectedIds = new Set(protectedItems.map((item) => item.id));
  for (const track of snapshot.tracks) {
    for (const clip of track.clips) {
      if (clip.id && !affectedIds.has(clip.id) && !alreadyProtectedIds.has(clip.id)) {
        protectedItems.push(editItemTarget(clip, track, "protected_neighbor"));
      }
    }
  }
  const clipsById = new Map(snapshot.tracks.flatMap((track) => track.clips.filter((clip) => clip.id).map((clip) => [clip.id, clip])));
  const replacementIndexes = expectedItems.flatMap((item, index) => item.role === "replacement" ? [index] : []);
  const preservedIndexes = expectedItems.flatMap((item, index) => item.role === "preserved_edge" ? [index] : []);
  const preservedOriginals = new Map(preservedIndexes.map((index) => {
    const original = clipsById.get(expectedItems[index].beforeItemId);
    if (!original || original.linkedItemIds === null) {
      throw new SdkLiveInspectionError("INVALID_RESPONSE", "A preserved edit edge lacked authoritative linked-item topology.");
    }
    return [index, original];
  }));
  const preservedAdjacent = (leftIndex, rightIndex) => {
    const left = expectedItems[leftIndex];
    const right = expectedItems[rightIndex];
    const leftOriginal = preservedOriginals.get(leftIndex);
    const rightOriginal = preservedOriginals.get(rightIndex);
    return left.preservedEdgeSide === right.preservedEdgeSide
      && (leftOriginal.linkedItemIds.includes(right.beforeItemId)
        || rightOriginal.linkedItemIds.includes(left.beforeItemId)
        || left.mediaPoolItemId === right.mediaPoolItemId
          && left.recordRange.start === right.recordRange.start
          && left.track.type !== right.track.type);
  };
  const preservedComponent = (startIndex) => {
    const visited = new Set([startIndex]);
    const pending = [startIndex];
    while (pending.length > 0) {
      const current = pending.pop();
      for (const candidate of preservedIndexes) {
        if (!visited.has(candidate) && preservedAdjacent(current, candidate)) {
          visited.add(candidate);
          pending.push(candidate);
        }
      }
    }
    return [...visited].filter((index) => index !== startIndex);
  };
  const expectedItemsWithTopology = expectedItems.map((item, index) => {
    if (item.role === "replacement") {
      return {
        ...item,
        linkedExpectedItemIndexes: intent.linkedAudio === "include" ? replacementIndexes.filter((candidate) => candidate !== index) : [],
        linkedExistingItemIds: [],
      };
    }
    if (item.role !== "preserved_edge") {
      if (item.role === "trimmed" && intent.action === "trim") {
        const original = clipsById.get(item.beforeItemId);
        if (!original || original.linkedItemIds === null) {
          throw new SdkLiveInspectionError("INVALID_RESPONSE", "A linked trim result lacked authoritative original topology.");
        }
        if (intent.linkedAudio === "exclude") {
          return { ...item, linkedExpectedItemIndexes: [], linkedExistingItemIds: [...original.linkedItemIds] };
        }
        const linkedExpectedItemIndexes = expectedItems.flatMap((candidate, candidateIndex) => (
          candidate.role === "trimmed" && original.linkedItemIds.includes(candidate.beforeItemId) ? [candidateIndex] : []
        ));
        if (linkedExpectedItemIndexes.length !== original.linkedItemIds.length) {
          throw new SdkLiveInspectionError("INVALID_RESPONSE", "The linked trim result did not cover the complete original topology.");
        }
        return { ...item, linkedExpectedItemIndexes, linkedExistingItemIds: [] };
      }
      return { ...item, linkedExpectedItemIndexes: [], linkedExistingItemIds: [] };
    }
    const { preservedEdgeSide: _preservedEdgeSide, ...publicItem } = item;
    return {
      ...publicItem,
      linkedExpectedItemIndexes: preservedComponent(index),
      linkedExistingItemIds: [],
    };
  });
  const protectedById = new Map(protectedItems.filter((item) => !affectedIds.has(item.id)).map((item) => [item.id, item]));
  const affectedTracksById = new Map(affectedTracks.map((track) => [`${track.type}:${track.index}`, track]));
  const candidate = {
    action: intent.action,
    projectId: intent.projectId,
    timelineId: intent.timelineId,
    timelineRevision: intent.timelineRevision,
    intent,
    recordRange,
    affectedTracks: [...affectedTracksById.values()],
    affectedItems,
    protectedItems: [...protectedById.values()],
    expectedItems: expectedItemsWithTopology,
    linkedAudio: { behavior: intent.linkedAudio, topologyProven },
    capabilityId: intent.action === "trim" ? "edit.trim_workaround" : "edit.insert_overwrite",
    summary: intent.action === "trim"
      ? `Trim ${affectedItems.length} exact timeline item${affectedItems.length === 1 ? "" : "s"} while preserving ${protectedById.size} resolved targets.`
      : `${intent.action === "insert" ? "Insert" : "Overwrite"} one source range on ${affectedTracksById.size} exact track${affectedTracksById.size === 1 ? "" : "s"}; ${affectedItems.length} existing items are affected.`,
  };
  return finalizeTimelineEditImpact(candidate);
}

function normalizeColorTarget(raw, before, after, revisionEvidenceKey, request) {
  if (!raw.color_before && !raw.color_after) {
    throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The current DaVinci Resolve timeline has no active video Color target.");
  }
  if (!raw.color_before || !raw.color_after) {
    throw new SdkLiveInspectionError("STALE_REVISION", "The active Color target changed while CutAgent was reading it.");
  }
  if (JSON.stringify(canonicalize(raw.color_before)) !== JSON.stringify(canonicalize(raw.color_after))) {
    throw new SdkLiveInspectionError("STALE_REVISION", "The active Color target or grade changed while CutAgent was reading it.");
  }
  const nativeTargetId = text(raw.color_before.target?.timeline_item_unique_id);
  if (!nativeTargetId) return malformed("CutAgent CLI did not return an authoritative Color target identity.");
  if (!raw.summary_before || !raw.summary_after) {
    return malformed("CutAgent CLI did not bracket the Color target with authoritative timeline snapshots.");
  }
  if (JSON.stringify(canonicalize(raw.summary_before)) !== JSON.stringify(canonicalize(raw.summary_after))) {
    throw new SdkLiveInspectionError("STALE_REVISION", "The active Color target placement changed while CutAgent was reading it.");
  }
  const snapshot = normalizeSnapshot(raw.summary_after, before, after, revisionEvidenceKey);
  const durableTargetId = digest("timeline_item_", { timelineId: before.timeline.id, nativeId: nativeTargetId });
  const matches = snapshot.tracks.flatMap((track) => (
    track.type === "video"
      ? track.clips.filter((clip) => clip.id === durableTargetId).map((clip) => ({ track, clip }))
      : []
  ));
  if (matches.length === 0) {
    throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The active Color target is not present in the exact current timeline snapshot.");
  }
  if (matches.length > 1) {
    throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "The active Color target is ambiguous in the current timeline snapshot.");
  }
  const match = matches[0];
  if (!match) return malformed("CutAgent could not resolve the validated Color target.");
  const graph = raw.color_before.node_graph;
  const nodeStackLayerIndex = integer(graph?.node_stack_layer_index);
  const requestedNodeStackLayerIndex = request.nodeStackLayerIndex ?? 1;
  if (nodeStackLayerIndex === null || nodeStackLayerIndex !== requestedNodeStackLayerIndex) {
    return malformed("CutAgent CLI returned the wrong Color node-stack layer.");
  }
  const rawNodes = Array.isArray(graph?.nodes) ? graph.nodes : null;
  const nodeCount = integer(graph?.node_count);
  if (rawNodes === null || nodeCount === null || nodeCount !== rawNodes.length) {
    return malformed("CutAgent CLI returned malformed Color node graph metadata.");
  }
  const exposeEffects = raw.color_before.capabilities?.effects?.status === "supported";
  const nodes = rawNodes.map((node, offset) => {
    const index = integer(node?.index);
    if (index !== offset + 1) return malformed("CutAgent CLI returned out-of-order Color node metadata.");
    const effects = Array.isArray(node.effects)
      ? exposeEffects ? node.effects.map(publicEffect) : []
      : malformed("CutAgent CLI returned malformed Color effect metadata.");
    if (node.label !== null && typeof node.label !== "string") {
      return malformed("CutAgent CLI returned malformed Color node-label metadata.");
    }
    return {
      index,
      label: node.label === null ? null : text(node.label),
      enabled: typeof node.enabled === "boolean" ? node.enabled : null,
      lut: publicLut(node.lut),
      effects,
    };
  });
  const capabilities = raw.color_before.capabilities;
  const versions = raw.color_before.versions;
  if (!capabilities || !versions || !Array.isArray(versions.local) || !Array.isArray(versions.remote)) {
    return malformed("CutAgent CLI returned malformed Color inspection metadata.");
  }
  const normalizedVersions = {
    current: versions.current === null ? null : text(versions.current),
    local: versions.local.map(text).filter(Boolean),
    remote: versions.remote.map(text).filter(Boolean),
  };
  const colorRevision = `revision_f${privateEvidenceDigest(revisionEvidenceKey, {
    domain: "color.current.revision.v1",
    timelineRevision: snapshot.revision,
    nodeStackLayerIndex,
    color: raw.color_before,
  })}`;
  return parseRuntime(sdkColorTargetSnapshotSchema, {
    project: snapshot.project,
    timeline: snapshot.timeline,
    revision: colorRevision,
    timelineRevision: snapshot.revision,
    nodeStackLayerIndex,
    frameRate: snapshot.frameRate,
    track: {
      snapshotId: match.track.snapshotId,
      index: match.track.index,
      name: match.track.name,
    },
    clip: match.clip,
    capabilities: {
      nodeGraph: colorCapability(capabilities.nodeGraph),
      labels: colorCapability(capabilities.labels),
      enabledState: colorCapability(capabilities.enabledState),
      luts: colorCapability(capabilities.luts),
      effects: colorCapability(capabilities.effects),
      versions: colorCapability(capabilities.versions),
      colorGroup: colorCapability(capabilities.colorGroup),
    },
    mutationCapabilities: {
      primary: { status: "runtime_check_required", edition: "studio_or_free", projectStorage: "disk_required", plugin: "not_required" },
      nodes: { status: "runtime_check_required", edition: "studio_or_free", projectStorage: "disk_required", plugin: "not_required" },
      lutAssets: { status: "runtime_check_required", edition: "studio_or_free", projectStorage: "any", plugin: "not_required" },
      drxAssets: { status: "runtime_check_required", edition: "studio_or_free", projectStorage: "disk_required", plugin: "not_required" },
      effects: { status: "runtime_check_required", edition: "studio_or_free", projectStorage: "disk_required", plugin: "installed_effect_required" },
    },
    nodeGraph: { nodeCount, nodes },
    versions: normalizedVersions,
    colorGroup: raw.color_before.color_group === null ? null : text(raw.color_before.color_group),
  }, "CutAgent CLI returned a Color target snapshot that violated the SDK contract.");
}

function privateColorVerificationState(raw) {
  const color = raw?.color_before;
  const nodes = color?.node_graph?.nodes;
  const grade = color?.grade_state;
  if (!color || !Array.isArray(nodes)) return malformed("CutAgent CLI omitted private Color verification state.");
  let normalizedGrade = null;
  if (grade !== null && grade !== undefined) {
    if (!grade || typeof grade !== "object" || !/^[a-f0-9]{64}$/.test(grade.sha256)
      || typeof grade.has_grade !== "boolean" || !Number.isSafeInteger(grade.raw_param_count)
      || !grade.primary_by_node || typeof grade.primary_by_node !== "object" || Array.isArray(grade.primary_by_node)
      || !grade.topology || !["serial", "parallel", "layer", "unknown"].includes(grade.topology.kind)
      || !Number.isSafeInteger(grade.topology.node_count) || grade.topology.node_count < 0) {
      return malformed("CutAgent CLI returned malformed private Color grade verification state.");
    }
    const primaryByNode = {};
    for (const [node, values] of Object.entries(grade.primary_by_node)) {
      if (!/^[1-9][0-9]{0,3}$/.test(node) || !values || typeof values !== "object" || Array.isArray(values)) {
        return malformed("CutAgent CLI returned malformed private Color primary readback.");
      }
      primaryByNode[node] = Object.fromEntries(Object.entries(values).map(([name, value]) => {
        if (!/^(contrast|pivot|temperature|tint|hue|color_boost|mid_detail|shadows|highlights)$/.test(name)
          || typeof value !== "number" || !Number.isFinite(value)) {
          return malformed("CutAgent CLI returned malformed private Color primary readback.");
        }
        return [name, value];
      }));
    }
    const topology = grade.topology;
    if (typeof topology.exact !== "boolean" || !/^[a-f0-9]{64}$/.test(topology.structure_sha256)
      || !Array.isArray(topology.containers) || topology.containers.length !== topology.node_count
      || !Array.isArray(topology.edges) || !topology.render || typeof topology.render !== "object") {
      return malformed("CutAgent CLI returned malformed private Color topology proof.");
    }
    const containerDigests = topology.containers.map((container, offset) => {
      if (!container || typeof container !== "object" || container.position !== offset + 1
        || !/^[a-f0-9]{64}$/.test(container.sha256) || !Number.isSafeInteger(container.node_index)
        || !Number.isSafeInteger(container.node_type)) {
        return malformed("CutAgent CLI returned malformed private Color container proof.");
      }
      return container.sha256;
    });
    const renderDigests = [topology.render.field9_sha256, topology.render.field10_sha256];
    if (renderDigests.some((value) => value !== null && (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value)))) {
      return malformed("CutAgent CLI returned malformed private Color render-graph proof.");
    }
    if (!grade.resolvefx_by_node || typeof grade.resolvefx_by_node !== "object" || Array.isArray(grade.resolvefx_by_node)) {
      return malformed("CutAgent CLI omitted private ResolveFX occupancy proof.");
    }
    const resolveFxByNode = {};
    for (const [node, pluginId] of Object.entries(grade.resolvefx_by_node)) {
      if (!/^[1-9][0-9]{0,3}$/.test(node) || (pluginId !== null && (typeof pluginId !== "string" || !/^com\.blackmagicdesign\.resolvefx\.[a-z0-9]+$/.test(pluginId)))) {
        return malformed("CutAgent CLI returned malformed private ResolveFX occupancy proof.");
      }
      resolveFxByNode[node] = pluginId;
    }
    if (Object.keys(resolveFxByNode).length !== topology.node_count
      || Array.from({ length: topology.node_count }, (_value, index) => String(index + 1)).some((node) => !(node in resolveFxByNode))) {
      return malformed("CutAgent CLI returned incomplete private ResolveFX occupancy proof.");
    }
    normalizedGrade = { sha256: grade.sha256, hasGrade: grade.has_grade, rawParamCount: grade.raw_param_count, primaryByNode,
      resolveFxByNode,
      topology: { kind: topology.kind, nodeCount: topology.node_count, exact: topology.exact,
        structureSha256: topology.structure_sha256, containerDigests, renderDigests } };
  }
  return Object.freeze({
    grade: normalizedGrade,
    nodes: nodes.map((node) => Object.freeze({
      index: node.index,
      lutDigest: typeof node.lut === "string" && node.lut ? privateTextDigest(node.lut) : null,
      effects: Array.isArray(node.effects) ? node.effects.map(publicEffect) : malformed("CutAgent CLI returned malformed private Color effect readback."),
    })),
  });
}

function assertExpected(actual, expectedProjectId, expectedTimelineId = null) {
  if (actual.project.id !== expectedProjectId || (expectedTimelineId && actual.timeline.id !== expectedTimelineId)) {
    throw new SdkLiveInspectionError("STALE_REVISION", "The referenced DaVinci Resolve object is no longer current.");
  }
}

function normalizeMulticam(raw, project, request, revisionEvidenceKey) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.angles)) {
    return malformed("CutAgent CLI returned malformed multicam inspection data.");
  }
  const name = text(raw.name);
  const nativeId = text(raw.native_id);
  if (!name || name.length > 1024 || name !== request.multicamName || !nativeId) {
    return malformed("CutAgent CLI did not prove the requested native multicam identity.");
  }
  const mediaPoolItemId = digest("media_pool_item_", { projectId: project.id, nativeId });
  if (mediaPoolItemId !== request.mediaPoolItemId) {
    throw new SdkLiveInspectionError("STALE_REVISION", "The referenced multicam asset is no longer current.");
  }
  const multicamId = digest("multicam_", { projectId: project.id, nativeId });
  const sourceIds = new Set();
  const angles = raw.angles.map((angle) => {
    const index = strictInteger(angle?.angle_index);
    const label = text(angle?.label);
    const videoLabel = text(angle?.video_label);
    const audioLabel = text(angle?.audio_label);
    const videoEnabled = typeof angle?.video_enabled === "boolean" ? angle.video_enabled : null;
    const audioEnabled = typeof angle?.audio_enabled === "boolean" ? angle.audio_enabled : null;
    if (index === null || index < 0 || index > 5 || !label || !videoLabel || !audioLabel || videoEnabled === null || audioEnabled === null
      || !Array.isArray(angle.sources) || angle.sources.length === 0 || !Array.isArray(angle.audio_sources)) {
      return malformed("CutAgent CLI returned an invalid multicam angle.");
    }
    const normalizeSourceEvidence = (source, publicSource) => {
      const sourceName = text(source?.name);
      const sourceNativeId = text(source?.native_id);
      const databaseNativeId = text(source?.database_native_id) || sourceNativeId;
      if (!sourceName || sourceName.length > 1024 || !sourceNativeId) return malformed("CutAgent CLI did not prove a multicam source identity.");
      const itemIndex = strictInteger(source?.item_index);
      const trackNativeId = text(source?.track_native_id);
      const startFrame = strictInteger(source?.start_frame);
      const durationFrames = strictInteger(source?.duration_frames);
      const sourceInFrame = strictInteger(source?.source_in_frame);
      const selectorIndex = source?.selector_index === null ? null : strictInteger(source?.selector_index);
      const selectorSignature = source?.selector_signature === null ? null : text(source?.selector_signature);
      const gradeRevisionDigest = source?.grade_revision_digest === null ? null : text(source?.grade_revision_digest);
      const propertiesDigest = text(source?.properties_digest);
      const metadataDigest = text(source?.metadata_digest);
      if (!trackNativeId || itemIndex === null || itemIndex < 0 || startFrame === null || durationFrames === null || durationFrames < 1 || sourceInFrame === null || sourceInFrame < 0) {
        return malformed("CutAgent CLI returned invalid multicam source timing evidence.");
      }
      if ((source?.selector_index !== null && (selectorIndex === null || selectorIndex < 0))
        || (source?.selector_signature !== null && !selectorSignature)
        || (source?.grade_revision_digest !== null && !/^[0-9a-f]{64}$/.test(gradeRevisionDigest ?? ""))
        || !/^[0-9a-f]{64}$/.test(propertiesDigest ?? "") || !/^[0-9a-f]{64}$/.test(metadataDigest ?? "")) {
        return malformed("CutAgent CLI returned invalid private multicam source revision evidence.");
      }
      const sourceId = digest("media_pool_item_", { projectId: project.id, nativeId: sourceNativeId });
      if (publicSource) {
        if (sourceIds.has(sourceId)) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "A multicam source was assigned to more than one angle.");
        sourceIds.add(sourceId);
      }
      return {
        value: publicSource ? { mediaPoolItemId: sourceId, name: sourceName } : null,
        privateBinding: Object.freeze({ mediaPoolItemId: sourceId, nativeId: databaseNativeId, trackNativeId, itemIndex, startFrame, durationFrames }),
        revisionEvidence: privateEvidenceDigest(revisionEvidenceKey, {
          sourceNativeId, databaseNativeId, itemIndex, startFrame, durationFrames, sourceInFrame,
          selectorIndex, selectorSignature, gradeRevisionDigest, propertiesDigest, metadataDigest,
        }),
      };
    };
    const normalizedSources = angle.sources.map((source) => normalizeSourceEvidence(source, true));
    const normalizedAudioSources = angle.audio_sources.map((source) => normalizeSourceEvidence(source, false));
    const angleTrackNativeId = normalizedSources[0]?.privateBinding.trackNativeId;
    if (!angleTrackNativeId || normalizedSources.some((source) => source.privateBinding.trackNativeId !== angleTrackNativeId)) {
      return malformed("CutAgent CLI did not prove one stable native video track identity for the multicam angle.");
    }
    return {
      value: {
        id: digest("multicam_angle_", { multicamId, trackNativeId: angleTrackNativeId }),
        label,
        enabled: videoEnabled === audioEnabled ? videoEnabled : null,
        sources: normalizedSources.map((source) => source.value),
      },
      revisionEvidence: {
        videoLabel,
        audioLabel,
        videoEnabled,
        audioEnabled,
        videoSources: normalizedSources.map((source) => source.revisionEvidence),
        audioSources: normalizedAudioSources.map((source) => source.revisionEvidence),
      },
      privateBindings: Object.freeze({
        video: Object.freeze(normalizedSources.map((source) => source.privateBinding)),
        audio: Object.freeze(normalizedAudioSources.map((source) => source.privateBinding)),
      }),
    };
  });
  if (angles.some((angle, offset) => strictInteger(raw.angles[offset]?.angle_index) !== offset)) {
    return malformed("CutAgent CLI returned non-contiguous multicam angle identities.");
  }
  const sequenceStartFrame = raw.sequence_start_frame == null ? null : strictInteger(raw.sequence_start_frame);
  const sequenceDurationFrames = raw.sequence_duration_frames == null ? null : strictInteger(raw.sequence_duration_frames);
  if ((raw.sequence_start_frame != null && sequenceStartFrame === null)
    || (raw.sequence_duration_frames != null && (sequenceDurationFrames === null || sequenceDurationFrames < 1))) {
    return malformed("CutAgent CLI returned invalid multicam sequence timing evidence.");
  }
  const publicState = { id: multicamId, projectId: project.id, name, angles: angles.map((angle) => angle.value) };
  const value = parseRuntime(sdkMulticamSnapshotSchema, {
    ...publicState,
    revision: digest("revision_", {
      ...publicState,
      sequenceStartFrame,
      sequenceDurationFrames,
      timingEvidence: angles.map((angle) => angle.revisionEvidence),
    }),
  }, "CutAgent CLI returned a multicam snapshot that violated the SDK contract.");
  return Object.freeze({ value, privateSourceBindings: Object.freeze(angles.map((angle) => angle.privateBindings)) });
}

function normalizeFusionCompositions(raw, before, after, request, revisionEvidenceKey, normalizedSnapshot = null) {
  if (!raw || typeof raw !== "object" || !raw.timeline || !raw.fusion || !Array.isArray(raw.fusion.items)) {
    return malformed("CutAgent CLI returned malformed Fusion composition inspection data.");
  }
  const snapshot = normalizedSnapshot ?? normalizeSnapshot(raw.timeline, before, after, revisionEvidenceKey);
  if (request.expectedRevision !== null && snapshot.revision !== request.expectedRevision) {
    throw new SdkLiveInspectionError("STALE_REVISION", "The timeline snapshot changed before Fusion composition inspection completed.");
  }
  const matches = raw.fusion.items.filter((row) => {
    const nativeItemId = text(row?.native_item_id);
    return nativeItemId && digest("timeline_item_", { timelineId: before.timeline.id, nativeId: nativeItemId }) === request.timelineItemId;
  });
  if (matches.length === 0) {
    throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The exact timeline item no longer exists.");
  }
  if (matches.length > 1) {
    throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "The exact timeline item matched more than one live native object.");
  }
  const compositions = matches[0]?.compositions;
  if (!Array.isArray(compositions)) return malformed("CutAgent CLI returned malformed Fusion composition rows.");
  const indexes = new Set();
  return compositions.map((row) => {
    const index = strictInteger(row?.index);
    const name = text(row?.name);
    if (index === null || index < 1 || index > 128 || !name || indexes.has(index)
      || !row.graph || typeof row.graph !== "object"
      || !/^sha256:[0-9a-f]{64}$/.test(row.graph_digest ?? "")) {
      return malformed("CutAgent CLI returned an invalid Fusion composition row.");
    }
    indexes.add(index);
    const graphDigest = row.graph_digest;
    const id = digest("fusion_comp_", {
      timelineItemId: request.timelineItemId,
      index,
    });
    return parseRuntime(sdkFusionCompositionReferenceSchema, {
      id,
      projectId: before.project.id,
      timelineId: before.timeline.id,
      timelineItemId: request.timelineItemId,
      index,
      name,
      projectRevision: snapshot.revision,
      timelineRevision: snapshot.revision,
      revision: digest("revision_", { snapshotRevision: snapshot.revision, id, name, graphDigest }),
      graphDigest,
    }, "CutAgent CLI returned an invalid Fusion composition reference.");
  });
}

function fusionProtectedTargets({ snapshot, references, projectLibraryId, declaredTargets }) {
  const inventory = new Map();
  const add = (target) => {
    if (!target?.stableId) return;
    const parsed = sdkStableMutationTargetSchema.parse(target);
    const key = `${parsed.kind}\0${parsed.stableId}`;
    if (inventory.has(key)) {
      throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned duplicate protected-target identities.");
    }
    inventory.set(key, parsed);
  };
  add({ kind: "project", stableId: snapshot.project.id, revision: snapshot.revision });
  add({ kind: "timeline", stableId: snapshot.timeline.id, revision: snapshot.revision });
  for (const track of snapshot.tracks) {
    add({
      kind: "track",
      stableId: track.snapshotId,
      revision: snapshot.revision,
      trackType: track.type,
      trackIndex: track.index,
    });
    for (const clip of track.clips) {
      add({ kind: "clip", stableId: clip.id, revision: snapshot.revision });
      if (clip.mediaPoolItemId && !inventory.has(`media\0${clip.mediaPoolItemId}`)) {
        add({ kind: "media", stableId: clip.mediaPoolItemId, revision: snapshot.revision });
      }
    }
  }
  for (const marker of snapshot.markers) {
    add({ kind: "marker", stableId: marker.id, revision: snapshot.revision });
  }
  for (const reference of references) {
    add({ kind: "fusion_composition", stableId: reference.id, revision: reference.revision });
  }
  return declaredTargets.map((declared) => {
    const parsed = sdkStableMutationTargetSchema.parse(declared);
    if (parsed.kind === "project_library") {
      if (!projectLibraryId || parsed.stableId !== projectLibraryId) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The protected project library no longer matches the active editing scope.");
      }
      return parsed;
    }
    const current = inventory.get(`${parsed.kind}\0${parsed.stableId}`);
    if (!current) {
      throw new SdkLiveInspectionError("STALE_REVISION", "A declared protected target no longer exists in the live Fusion inspection.");
    }
    return sdkStableMutationTargetSchema.parse({
      ...current,
      ...(parsed.mediaRole ? { mediaRole: parsed.mediaRole } : {}),
    });
  });
}

function readAfterBracket(reader, message) {
  try {
    return reader();
  } catch (error) {
    if (error instanceof SdkLiveInspectionError && error.code === "TARGET_NOT_FOUND") {
      throw new SdkLiveInspectionError("STALE_REVISION", message);
    }
    throw error;
  }
}

export function createSdkLiveInspectionService({
  resolveService,
  identityNamespace,
  defaultInternalInspectionTimeoutMs = DEFAULT_INTERNAL_INSPECTION_TIMEOUT_MS,
}) {
  if (typeof resolveService?.readSdkLiveInspection !== "function") {
    throw new TypeError("SDK live inspection requires the CutAgent CLI-backed resolve service.");
  }
  if (typeof identityNamespace !== "string" || !identityNamespace.trim()) {
    throw new TypeError("SDK live inspection requires a stable installation/profile identity namespace.");
  }
  if (!Number.isSafeInteger(defaultInternalInspectionTimeoutMs)
    || defaultInternalInspectionTimeoutMs < 100
    || defaultInternalInspectionTimeoutMs > 180_000) {
    throw new TypeError("SDK live inspection default deadline is invalid.");
  }
  const stableIdentityNamespace = identityNamespace.trim();
  // The namespace is a private, mode-0600 installation/profile secret. Derive
  // a domain-separated key so keyed snapshot revisions survive bridge/runtime
  // restarts without exposing native source evidence in the public revision.
  const revisionEvidenceKey = crypto
    .createHmac("sha256", stableIdentityNamespace)
    .update("cutagent-sdk-live-revision-evidence-v1", "utf8")
    .digest();
  const renderCursorKey = crypto
    .createHmac("sha256", stableIdentityNamespace)
    .update("cutagent-sdk-render-queue-cursor-v1", "utf8")
    .digest();
  const renderIdentityEvidenceKey = crypto
    .createHmac("sha256", stableIdentityNamespace)
    .update("cutagent-sdk-render-identity-evidence-v1", "utf8")
    .digest();
  const readSdkLiveInspection = (operation, options = {}) => resolveService.readSdkLiveInspection(
    operation,
    options.deadlineAtMs === undefined
      ? { ...options, deadlineAtMs: Date.now() + defaultInternalInspectionTimeoutMs }
      : options,
  );
  const inspect = async (request, options = {}) => {
      if (request.operation === "timeline.edit.preview") {
        return { value: await previewTimelineEdit(request.intent, options), mutationGuard: null };
      }
      if (request.operation === "timeline.retime") {
        const initial = await inspect({ operation: "timeline.snapshot", projectId: request.projectId, timelineId: request.timelineId }, options);
        if (initial.value.revision !== request.timelineRevision) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The retime target snapshot is stale.");
        }
        const initialTarget = exactRetimeTarget(initial.value, request.target);
        const privateId = initialTarget?.clip.id === null
          ? null
          : initial.privateTimelineItemNativeIdByPublicId?.get(initialTarget?.clip.id);
        if (!initialTarget || typeof privateId !== "string" || !privateId) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The exact retime target no longer exists at its snapshot coordinate.");
        }
        const publicClosureIds = [initialTarget.clip.id, ...initialTarget.clip.linkedItemIds];
        const publicClosure = publicClosureIds.map((id) => initial.value.tracks.flatMap((track) => track.clips
          .filter((clip) => clip.id === id).map((clip) => ({track, clip}))));
        if (new Set(publicClosureIds).size !== publicClosureIds.length || publicClosure.some((matches) => matches.length !== 1)
          || publicClosure.some(([entry]) => (!entry.clip.sourceRange && !entry.clip.retimeSource?.availableRange)
            || !Array.isArray(entry.clip.linkedItemIds))) {
          return malformed("CutAgent CLI omitted exact public linked-item identity for retime inspection.");
        }
        const privateTargets = publicClosure.map(([entry]) => ({
          id: initial.privateTimelineItemNativeIdByPublicId?.get(entry.clip.id),
          trackType: entry.track.type,
          trackIndex: entry.track.index,
          recordStartFrame: entry.clip.recordRange.start,
          recordEndFrame: entry.clip.recordRange.endExclusive,
          sourceStartFrame: (entry.clip.sourceRange ?? entry.clip.retimeSource.availableRange).start,
          sourceEndFrame: (entry.clip.sourceRange ?? entry.clip.retimeSource.availableRange).endExclusive,
          ...(entry.clip.sourceRange === null ? {sourceOriginFrame: entry.clip.retimeSource.originFrame} : {}),
          name: entry.clip.name,
          linkedItemIds: entry.clip.linkedItemIds.map((linkedId) => initial.privateTimelineItemNativeIdByPublicId?.get(linkedId)),
        }));
        if (privateTargets.some((target) => typeof target.id !== "string" || !target.id
          || target.linkedItemIds.some((value) => typeof value !== "string" || !value))) {
          return malformed("CutAgent CLI omitted exact private linked-item identity for retime inspection.");
        }
        const rawRetime = await readSdkLiveInspection("timeline.retime", {
          ...options,
          readRequest: request,
          privateTargets,
        });
        if (!rawRetime || typeof rawRetime !== "object") return malformed("CutAgent CLI returned no retime inspection result.");
        const before = liveIdentity(rawRetime.before, stableIdentityNamespace);
        const after = readAfterBracket(
          () => liveIdentity(rawRetime.after, stableIdentityNamespace),
          "The active project or timeline changed during retime inspection.",
        );
        assertExpected(before, request.projectId, request.timelineId);
        assertExpected(after, request.projectId, request.timelineId);
        const privateIds = new Map();
        const snapshot = normalizeSnapshot(rawRetime.summary, before, after, revisionEvidenceKey, privateIds);
        if (snapshot.revision !== request.timelineRevision || !exactRetimeTarget(snapshot, request.target)) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The timeline or exact retime target changed during inspection.");
        }
        if (privateIds.get(request.target.id) !== privateId) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The native retime target identity changed during inspection.");
        }
        const rows = rawRetime.summary?.retime?.rows;
        if (!Array.isArray(rows)) return malformed("CutAgent CLI omitted retime database rows.");
        const matches = rows.filter((row) => String(row?.Sm2TiItem_id ?? "") === privateId);
        const returnedIds = rows.map((row) => String(row?.Sm2TiItem_id ?? ""));
        if (rows.length !== privateTargets.length || new Set(returnedIds).size !== returnedIds.length
          || rows.some((row) => !privateTargets.some((target) => target.id === String(row?.Sm2TiItem_id ?? "")
            && target.trackType === row?.live_track_type && target.trackIndex === row?.live_track_index
            && row?.timeline_name === before.timeline.name)) || matches.length !== 1
          || matches[0].live_track_type !== initialTarget.track.type
          || matches[0].live_track_index !== initialTarget.track.index
          || matches[0].timeline_name !== before.timeline.name) {
          return malformed("CutAgent CLI returned ambiguous or wrong-target retime database evidence.");
        }
        const privateToPublicId = new Map(privateTargets.map((target, index) => [target.id, publicClosure[index][0].clip.id]));
        const retimeStates = rows.map((row) => normalizeRetimeState(row.state, privateToPublicId.get(String(row.Sm2TiItem_id))));
        const state = retimeStates.find((entry) => entry.timelineItemId === request.target.id);
        if (!state) return malformed("CutAgent CLI omitted the requested retime database state.");
        return {
          value: parseRuntime(sdkRetimeReadbackSchema, {
            projectId: request.projectId,
            timelineId: request.timelineId,
            timelineRevision: snapshot.revision,
            ...state,
          }, "CutAgent CLI returned retime state that violated the public SDK contract."),
          mutationGuard: null,
          privateRetimeStates: Object.freeze(retimeStates),
        };
      }
      const raw = await readSdkLiveInspection(
        request.operation === "timeline.list" ? "project.context" : request.operation,
        { ...options, readRequest: request },
      );
      if (!raw || typeof raw !== "object") return malformed("CutAgent CLI returned no live inspection result.");
      if (request.operation.startsWith("render.")) {
        if (raw.context_unchanged !== true) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The DaVinci Resolve project, timeline, page, render settings, or queue changed during render inspection.");
        }
        const beforeProject = renderProject(raw.before, stableIdentityNamespace);
        const afterProject = renderProject(raw.after, stableIdentityNamespace);
        if (beforeProject.id !== afterProject.id || beforeProject.name !== afterProject.name || beforeProject.id !== request.projectId) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The referenced DaVinci Resolve project changed during render inspection.");
        }
        if (request.operation === "render.discovery") {
          return { value: normalizeRenderDiscovery(raw.discovery, beforeProject.id), mutationGuard: null };
        }
        if (request.operation === "render.presets") {
          return { value: normalizeRenderPresets(raw.presets, beforeProject.id), mutationGuard: null };
        }
        const queue = queueState(raw.jobs, beforeProject.id, renderIdentityEvidenceKey);
        if (request.operation === "render.settings") {
          const settings = normalizeRenderSettings(raw.settings, beforeProject.id);
          return { value: parseRuntime(sdkRenderSettingsSnapshotSchema, {
            ...settings,
            revision: digest("revision_", settings),
            queueCount: queue.jobs.length,
          }, "CutAgent CLI returned render settings that violated the SDK contract."), mutationGuard: null };
        }
        if (request.operation === "render.queue") {
          const offset = parseCursor(renderCursorKey, request.cursor, queue.queueRevision);
          if (offset > queue.jobs.length) throw new SdkLiveInspectionError("STALE_REVISION", "The render queue page cursor is no longer valid.");
          const jobs = queue.jobs.slice(offset, offset + request.pageSize);
          const nextOffset = offset + jobs.length;
          return { value: parseRuntime(sdkRenderQueuePageSchema, {
            projectId: beforeProject.id,
            queueRevision: queue.queueRevision,
            support: queue.support,
            cursor: request.cursor,
            offset,
            pageSize: request.pageSize,
            jobs,
            nextCursor: nextOffset < queue.jobs.length ? cursorToken(renderCursorKey, queue.queueRevision, nextOffset) : null,
            total: queue.jobs.length,
          }, "CutAgent CLI returned a render queue page that violated the SDK contract."), mutationGuard: null };
        }
        if (request.queueRevision !== queue.queueRevision) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The render queue changed after this job reference was observed.");
        }
        const matches = queue.jobs.filter((job) => job.id === request.jobId);
        if (matches.length === 0) throw new SdkLiveInspectionError("STALE_REVISION", "The referenced render job is no longer present in this queue snapshot.");
        if (matches.length > 1) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "The render job reference is ambiguous in this queue snapshot.");
        return { value: parseRuntime(sdkRenderJobStatusSnapshotSchema, {
          projectId: beforeProject.id,
          queueRevision: queue.queueRevision,
          support: queue.support,
          job: matches[0],
        }, "CutAgent CLI returned render job status that violated the SDK contract."), mutationGuard: null };
      }
      if (["project.context", "project.folder_context", "project.library_context"].includes(request.operation)) {
        if (JSON.stringify(canonicalize(raw.before)) !== JSON.stringify(canonicalize(raw.after))) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The project context changed while CutAgent was reading it.");
        }
        const mutationGuard = typeof raw.mutation_guard === "string" && /^sha256:[a-f0-9]{64}$/.test(raw.mutation_guard)
          ? raw.mutation_guard
          : malformed("CutAgent CLI omitted the exact project-context mutation guard.");
        const value = projectContext(raw.after, stableIdentityNamespace);
        const nativeProjectLibrary = privateProjectLibraryIdentity(raw.after);
        const projectLibraryId = value.library === null
          ? null
          : digest("project_library_", { identityNamespace: stableIdentityNamespace, library: nativeProjectLibrary });
        const nativeProjectId = value.project === null ? null : text(raw.after?.project?.project_id);
        const nativeTimelineId = value.timeline === null ? null : currentTimeline(raw.after, value.project).nativeId;
        const nativeProjectFolder = raw.after?.project_folder;
        const nativeProjectLibraries = request.operation === "project.library_context"
          ? privateProjectLibraryInventory(raw.after, stableIdentityNamespace, nativeProjectLibrary)
          : null;
        if (value.project !== null && !nativeProjectId) {
          return malformed("CutAgent CLI omitted the exact native project identity.");
        }
        return {
          value,
          mutationGuard,
          privateExecutionIdentity: {
            projectLibraryId,
            nativeProjectId,
            nativeTimelineId,
            nativeProjectLibrary,
            nativeProjectLibraries,
            nativeProjectFolder: nativeProjectFolder && typeof nativeProjectFolder === "object"
              ? {
                  path: text(nativeProjectFolder.path),
                  nativeId: text(nativeProjectFolder.native_id),
                  openProjectNativeId: text(nativeProjectFolder.open_project_native_id),
                  children: Array.isArray(nativeProjectFolder.children) ? nativeProjectFolder.children.map((child) => ({
                    name: text(child?.name), path: text(child?.path), nativeId: text(child?.native_id),
                  })) : [],
                  projects: Array.isArray(nativeProjectFolder.projects) ? nativeProjectFolder.projects.map(text) : [],
                  projectRecords: Array.isArray(nativeProjectFolder.project_records) ? nativeProjectFolder.project_records.map((project) => ({
                    name: text(project?.name), nativeId: text(project?.native_id),
                  })) : [],
                  ancestors: Array.isArray(nativeProjectFolder.ancestors) ? nativeProjectFolder.ancestors.map((ancestor) => ({
                    path: text(ancestor?.path), nativeId: text(ancestor?.native_id),
                  })) : [],
                }
              : null,
          },
        };
      }
      if (request.operation === "timeline.list") {
        if (JSON.stringify(canonicalize(raw.before)) !== JSON.stringify(canonicalize(raw.after))) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The project or Timeline inventory changed while CutAgent was reading it.");
        }
        const beforeProject = currentProject(raw.before, stableIdentityNamespace);
        const afterProject = currentProject(raw.after, stableIdentityNamespace);
        assertExpected({ project: beforeProject }, request.projectId);
        if (beforeProject.id !== afterProject.id || beforeProject.name !== afterProject.name) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed while CutAgent was reading its Timeline inventory.");
        }
        const collectionRevision = projectContext(raw.after, stableIdentityNamespace).projectRevision.revision;
        if (request.expectedRevision !== undefined && request.expectedRevision !== collectionRevision) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The expected Timeline inventory revision is stale.");
        }
        const rows = raw.after?.timelines;
        if (!Array.isArray(rows) || rows.length > 10_000) {
          return malformed("CutAgent CLI returned an invalid or unbounded Timeline inventory.");
        }
        const seenNativeIds = new Set();
        const timelines = rows.map((row) => {
          const nativeId = text(row?.timeline_id);
          const name = text(row?.name);
          if (!nativeId || !name || seenNativeIds.has(nativeId)) {
            throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned an incomplete or ambiguous Timeline identity.");
          }
          seenNativeIds.add(nativeId);
          return {
            timelineId: digest("timeline_", { projectId: beforeProject.id, nativeId }),
            projectId: beforeProject.id,
            revision: digest("revision_", row),
            name,
          };
        });
        return { value: Object.freeze(timelines), mutationGuard: null };
      }
      if (request.operation === "project.current") {
        const beforeProject = currentProject(raw.before, stableIdentityNamespace);
        const afterProject = readAfterBracket(
          () => currentProject(raw.after, stableIdentityNamespace),
          "The active project changed while CutAgent was reading it.",
        );
        if (beforeProject.id !== afterProject.id || beforeProject.name !== afterProject.name) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed while CutAgent was reading it.");
        }
        return { value: beforeProject, mutationGuard: null };
      }
      if (request.operation === "mediaPool.page") {
        const beforeProject = currentProject(raw.before, stableIdentityNamespace);
        assertExpected({ project: beforeProject }, request.projectId);
        const afterProject = readAfterBracket(
          () => currentProject(raw.after, stableIdentityNamespace),
          "The active project changed while CutAgent was reading its Media Pool.",
        );
        if (beforeProject.id !== afterProject.id || beforeProject.name !== afterProject.name) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed while CutAgent was reading its Media Pool.");
        }
        const mutationGuard = raw.mutation_guard == null
          ? null
          : typeof raw.mutation_guard === "string" && /^sha256:[a-f0-9]{64}$/.test(raw.mutation_guard)
            ? raw.mutation_guard
            : malformed("CutAgent CLI returned a malformed Media Pool mutation guard.");
        const normalized = normalizeMediaPoolPage(raw.summary, beforeProject, request);
        return { ...normalized, mutationGuard };
      }
      if (request.operation === "multicam.inspect") {
        const beforeProject = currentProject(raw.before, stableIdentityNamespace);
        assertExpected({ project: beforeProject }, request.projectId);
        const afterProject = readAfterBracket(
          () => currentProject(raw.after, stableIdentityNamespace),
          "The active project changed while CutAgent was reading its multicam clip.",
        );
        if (beforeProject.id !== afterProject.id || beforeProject.name !== afterProject.name) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed while CutAgent was reading its multicam clip.");
        }
        const normalized = normalizeMulticam(raw.summary, beforeProject, request, revisionEvidenceKey);
        if (request.expectedRevision !== null && normalized.value.revision !== request.expectedRevision) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The referenced multicam revision is stale.");
        }
        return { value: normalized.value, mutationGuard: null, privateMulticamSourceBindings: normalized.privateSourceBindings };
      }
      const before = liveIdentity(raw.before, stableIdentityNamespace);
      assertExpected(before, request.projectId, new Set(["timeline.snapshot", "color.current", "fusion.compositions"]).has(request.operation) ? request.timelineId : null);
      const after = readAfterBracket(
        () => liveIdentity(raw.after, stableIdentityNamespace),
        "The active project or timeline changed while CutAgent was reading it.",
      );
      if (
        before.project.id !== after.project.id
        || before.project.name !== after.project.name
        || before.projectNativeId !== after.projectNativeId
        || before.timeline.id !== after.timeline.id
        || before.timeline.name !== after.timeline.name
        || before.timelineNativeId !== after.timelineNativeId
      ) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The active project or timeline changed while CutAgent was reading it.");
      }
      if (request.operation === "timeline.current") {
        const nativeProjectId = text(raw.before?.project?.project_id);
        const currentNativeTimelines = Array.isArray(raw.before?.timelines)
          ? raw.before.timelines.filter((timeline) => timeline?.is_current === true || timeline?.current === "yes")
          : [];
        const nativeTimelineId = currentNativeTimelines.length === 1 ? text(currentNativeTimelines[0]?.timeline_id) : null;
        const nativeTimelineMediaPoolItemId = text(raw.before?.current_timeline_media_pool_item_id);
        if (!nativeProjectId || !nativeTimelineId || !nativeTimelineMediaPoolItemId) return malformed("CutAgent CLI omitted the exact native execution identities for the current timeline.");
        return { value: before.timeline, mutationGuard: null, privateExecutionIdentity: { nativeProjectId, nativeTimelineId, nativeTimelineMediaPoolItemId } };
      }
      assertExpected(after, request.projectId, request.timelineId);
      if (request.operation === "color.current") {
        const mutationGuard = raw.mutation_guard == null
          ? null
          : typeof raw.mutation_guard === "string" && /^sha256:[a-f0-9]{64}$/.test(raw.mutation_guard)
            ? raw.mutation_guard
            : malformed("CutAgent CLI returned a malformed Color mutation guard.");
        return { value: normalizeColorTarget(raw, before, after, revisionEvidenceKey, request), mutationGuard, privateColorState: privateColorVerificationState(raw) };
      }
      if (request.operation === "fusion.compositions") {
        return { value: normalizeFusionCompositions(raw.summary, before, after, request, revisionEvidenceKey), mutationGuard: null };
      }
      const mutationGuard = typeof raw.mutation_guard === "string" && /^sha256:[a-f0-9]{64}$/.test(raw.mutation_guard)
        ? raw.mutation_guard
        : malformed("CutAgent CLI omitted the exact marker mutation guard.");
      const privateTimelineItemNativeIdByPublicId = new Map();
      const privateTimelineItemSourcePathByPublicId = new Map();
      const value = normalizeSnapshot(
        raw.summary,
        before,
        after,
        revisionEvidenceKey,
        privateTimelineItemNativeIdByPublicId,
        privateTimelineItemSourcePathByPublicId,
      );
      const inspectorByNativeId = new Map(raw.summary.tracks.flatMap((track) => (track.items ?? [])
        .filter((item) => typeof item.inspector_state_digest === "string" && /^[a-f0-9]{64}$/.test(item.inspector_state_digest))
        .map((item) => [item.timeline_item_unique_id, item.inspector_state_digest])));
      const privateInspectorStateDigestByPublicId = new Map([...privateTimelineItemNativeIdByPublicId]
        .filter(([, nativeId]) => inspectorByNativeId.has(nativeId))
        .map(([publicId, nativeId]) => [publicId, inspectorByNativeId.get(nativeId)]));
      const privateFairlightPlanReadback = normalizePrivateFairlightPlanReadback(
        raw.summary?.fairlight,
        privateTimelineItemNativeIdByPublicId,
        value,
      );
      return {
        value,
        mutationGuard,
        privateExecutionIdentity: {
          nativeProjectId: before.projectNativeId,
          nativeTimelineId: before.timelineNativeId,
        },
        privateTimelineItemNativeIdByPublicId,
        privateTimelineItemSourcePathByPublicId,
        privateFairlightPlanReadback,
        privateInspectorStateDigestByPublicId,
        nativeTimelineId: before.timelineNativeId,
      };
  };
  const resolveMediaPoolPrivateAsset = async (projectId, publicItemId, expectedRevision, options) => {
    let offset = 0;
    let observedRevision = expectedRevision;
    for (let pages = 0; pages < 31_250; pages += 1) {
      const readRequest = { operation: "mediaPool.page", projectId, offset, pageSize: 32, expectedRevision: offset === 0 ? null : observedRevision, search: null };
      const raw = await readSdkLiveInspection("mediaPool.page", { ...options, readRequest });
      const project = currentProject(raw.before, stableIdentityNamespace);
      assertExpected({ project }, projectId);
      const afterProject = readAfterBracket(
        () => currentProject(raw.after, stableIdentityNamespace),
        "The active project changed while CutAgent was resolving the selected Media Pool item.",
      );
      if (project.id !== afterProject.id || project.name !== afterProject.name) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed while CutAgent was resolving the selected Media Pool item.");
      }
      const { value: page } = normalizeMediaPoolPage(raw.summary, project, readRequest);
      if (observedRevision === null) observedRevision = page.revision;
      if (page.revision !== observedRevision) throw new SdkLiveInspectionError("STALE_REVISION", "The Media Pool changed after source selection.");
      const publicAsset = page.assets.find((asset) => asset.id === publicItemId);
      if (publicAsset) {
        const rawAsset = raw.summary.entries.find((entry) => entry.entry_kind === "asset"
          && text(entry.native_id)
          && digest("media_pool_item_", { projectId, nativeId: text(entry.native_id) }) === publicItemId);
        const nativeId = text(rawAsset?.native_id);
        if (!nativeId) throw new SdkLiveInspectionError("INVALID_RESPONSE", "The selected Media Pool item lost its authoritative native identity.");
        const sourcePath = text(rawAsset?.source_path);
        return Object.freeze({
          nativeId,
          name: publicAsset.name,
          sourcePath: sourcePath || null,
          revision: page.revision,
          poolDigest: raw.summary.pool_digest,
          kind: publicAsset.kind,
        });
      }
      if (page.nextOffset === null) break;
      offset = page.nextOffset;
    }
    throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The selected Media Pool item is no longer present.");
  };
  const resolveMediaPoolPrivateFolder = async (projectId, nativeFolderId, expectedRevision, options) => {
    const expectedNativeId = text(nativeFolderId);
    if (!expectedNativeId) throw new TypeError("Media Pool folder resolution requires an authoritative native identity.");
    let offset = 0;
    let observedRevision = expectedRevision;
    let match = null;
    for (let pages = 0; pages < 31_250; pages += 1) {
      const readRequest = { operation: "mediaPool.page", projectId, offset, pageSize: 32, expectedRevision: offset === 0 ? null : observedRevision, search: null };
      const raw = await readSdkLiveInspection("mediaPool.page", { ...options, readRequest });
      const project = currentProject(raw.before, stableIdentityNamespace);
      assertExpected({ project }, projectId);
      const afterProject = readAfterBracket(
        () => currentProject(raw.after, stableIdentityNamespace),
        "The active project changed while CutAgent was resolving the selected Media Pool folder.",
      );
      if (project.id !== afterProject.id || project.name !== afterProject.name) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed while CutAgent was resolving the selected Media Pool folder.");
      }
      const normalized = normalizeMediaPoolPage(raw.summary, project, readRequest);
      if (observedRevision === null) observedRevision = normalized.value.revision;
      if (normalized.value.revision !== observedRevision) throw new SdkLiveInspectionError("STALE_REVISION", "The Media Pool changed while resolving the selected folder.");
      for (const entry of normalized.privateMediaPoolState.entries) {
        if (entry.entryKind !== "folder" || entry.nativeId !== expectedNativeId) continue;
        if (match) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned duplicate Media Pool folder identities.");
        match = Object.freeze({
          nativeId: expectedNativeId,
          stableId: entry.id,
          name: entry.name,
          revision: normalized.value.revision,
        });
      }
      if (normalized.value.nextOffset === null) break;
      offset = normalized.value.nextOffset;
    }
    if (!match?.stableId) throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The selected Media Pool folder is no longer present.");
    return match;
  };
  const captureManagedTimelineAssets = async ({ projectId, timelineId, assetIds, expectedRevision = null }, options = {}) => {
    if (!Array.isArray(assetIds) || assetIds.length === 0 || assetIds.some((id) => !text(id))) {
      throw new TypeError("Managed Timeline asset capture requires at least one exact Media Pool item identity.");
    }
    const uniqueAssetIds = [...new Set(assetIds)];
    const timeline = await inspect({ operation: "timeline.current", projectId }, options);
    if (timeline.value.id !== timelineId) {
      throw new SdkLiveInspectionError("STALE_REVISION", "The managed Timeline is no longer current while refreshing its source assets.");
    }
    const nativeTimelineId = text(timeline.privateExecutionIdentity?.nativeTimelineId);
    const nativeTimelineMediaPoolItemId = text(timeline.privateExecutionIdentity?.nativeTimelineMediaPoolItemId);
    if (!nativeTimelineId || !nativeTimelineMediaPoolItemId) return malformed("CutAgent CLI omitted the exact native current Timeline binding.");
    let offset = 0;
    let revision = null;
    const privateEntries = [];
    const matches = new Map();
    for (let pages = 0; pages < 31_250; pages += 1) {
      const readRequest = { operation: "mediaPool.page", projectId, offset, pageSize: 32, expectedRevision: revision, search: null };
      const raw = await readSdkLiveInspection("mediaPool.page", { ...options, readRequest });
      const project = currentProject(raw.before, stableIdentityNamespace);
      assertExpected({ project }, projectId);
      const afterProject = readAfterBracket(
        () => currentProject(raw.after, stableIdentityNamespace),
        "The active project changed while CutAgent was refreshing managed Timeline assets.",
      );
      if (project.id !== afterProject.id || project.name !== afterProject.name) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed while CutAgent was refreshing managed Timeline assets.");
      }
      const normalized = normalizeMediaPoolPage(raw.summary, project, readRequest);
      revision ??= normalized.value.revision;
      if (normalized.value.revision !== revision) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The Media Pool changed while CutAgent was refreshing managed Timeline assets.");
      }
      privateEntries.push(...normalized.privateMediaPoolState.entries);
      for (const entry of normalized.privateMediaPoolState.entries) {
        if (entry.entryKind !== "asset" || !uniqueAssetIds.includes(entry.id)) continue;
        if (matches.has(entry.id)) {
          throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "A managed Timeline source has duplicate authoritative Media Pool identity.");
        }
        matches.set(entry.id, entry);
      }
      if (normalized.value.nextOffset === null) break;
      offset = normalized.value.nextOffset;
    }
    if (expectedRevision !== null && revision !== expectedRevision) {
      throw new SdkLiveInspectionError("STALE_REVISION", "The Media Pool changed after managed Timeline admission.");
    }
    if (uniqueAssetIds.some((id) => !matches.has(id))) {
      throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "A managed Timeline source is no longer present.");
    }
    const ownedTimelineEntries = privateEntries.filter((entry) => entry.entryKind === "asset" && entry.kind === "timeline"
      && entry.uniqueId === nativeTimelineMediaPoolItemId);
    if (ownedTimelineEntries.length !== 1) {
      throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "The managed Timeline has no unique Media Pool inventory identity.");
    }
    const afterTimeline = await inspect({ operation: "timeline.current", projectId }, options);
    if (afterTimeline.value.id !== timelineId
      || afterTimeline.privateExecutionIdentity?.nativeTimelineId !== nativeTimelineId
      || afterTimeline.privateExecutionIdentity?.nativeTimelineMediaPoolItemId !== nativeTimelineMediaPoolItemId) {
      throw new SdkLiveInspectionError("STALE_REVISION", "The current Timeline changed while CutAgent was refreshing managed Timeline assets.");
    }
    const ownedTimelineAssetId = ownedTimelineEntries[0].id;
    const stableInventory = privateEntries
      .filter((entry) => entry.id !== ownedTimelineAssetId)
      .map(managedMediaEntry);
    return Object.freeze({
      revision,
      stableInventoryDigest: privateTextDigest(JSON.stringify(canonicalize(stableInventory))),
      assets: Object.freeze(uniqueAssetIds.map((id) => Object.freeze({
        id,
        revision,
        fingerprint: privateTextDigest(JSON.stringify(canonicalize(managedMediaEntry(matches.get(id))))),
      }))),
    });
  };
  const resolveMediaPoolNativeIdentity = async (projectId, publicItemId, expectedRevision, options) => (
    await resolveMediaPoolPrivateAsset(projectId, publicItemId, expectedRevision, options)
  ).nativeId;
  const resolveMulticamPrivateTarget = async (projectId, multicamId, expectedRevision, options) => {
    let offset = 0;
    let observedRevision = null;
    for (let pages = 0; pages < 31_250; pages += 1) {
      const readRequest = { operation: "mediaPool.page", projectId, offset, pageSize: 32, expectedRevision: observedRevision, search: null };
      const raw = await readSdkLiveInspection("mediaPool.page", { ...options, readRequest });
      const project = currentProject(raw.before, stableIdentityNamespace);
      assertExpected({ project }, projectId);
      const afterProject = readAfterBracket(
        () => currentProject(raw.after, stableIdentityNamespace),
        "The active project changed while CutAgent was resolving the multicam target.",
      );
      if (project.id !== afterProject.id || project.name !== afterProject.name) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed while CutAgent was resolving the multicam target.");
      }
      const { value: page } = normalizeMediaPoolPage(raw.summary, project, readRequest);
      observedRevision ??= page.revision;
      const rawAsset = raw.summary.entries.find((entry) => entry.entry_kind === "asset"
        && entry.kind === "multicam" && text(entry.native_id)
        && digest("multicam_", { projectId, nativeId: text(entry.native_id) }) === multicamId);
      if (rawAsset) {
        const mediaPoolItemId = digest("media_pool_item_", { projectId, nativeId: text(rawAsset.native_id) });
        const request = { operation: "multicam.inspect", projectId, mediaPoolItemId, multicamName: mediaPoolName(rawAsset.name), expectedRevision };
        const inspected = await inspect(request, options);
        if (inspected.value.id !== multicamId) throw new SdkLiveInspectionError("STALE_REVISION", "The referenced multicam identity changed.");
        return Object.freeze({ value: inspected.value, name: inspected.value.name, nativeId: text(rawAsset.native_id), mediaPoolItemId,
          privateSourceBindings: inspected.privateMulticamSourceBindings });
      }
      if (page.nextOffset === null) break;
      offset = page.nextOffset;
    }
    throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The referenced multicam clip is no longer present.");
  };
  const prepareTimelineEdit = async (intent, options) => {
    if (typeof resolveService?.previewSdkTimelineEdit !== "function" || typeof resolveService?.readSdkCapability !== "function") {
      throw new TypeError("SDK timeline editing requires the CutAgent CLI-backed capability and preview boundaries.");
    }
    const capabilityId = intent.action === "trim" ? "edit.trim_workaround"
      : intent.action === "remove" ? "timeline.items_delete" : "edit.insert_overwrite";
    const capability = await resolveService.readSdkCapability(capabilityId, options);
    if (!capability.supported) {
      throw new SdkLiveInspectionError("CAPABILITY_UNAVAILABLE", capability.reason
        ? `The required CutAgent capability is unavailable: ${capability.reason}.`
        : "The required CutAgent capability is unavailable in the current DaVinci Resolve runtime.");
    }
    const snapshotRead = await inspect({ operation: "timeline.snapshot", projectId: intent.projectId, timelineId: intent.timelineId }, options);
    const snapshot = snapshotRead.value;
    if (snapshot.revision !== intent.timelineRevision) throw new SdkLiveInspectionError("STALE_REVISION", "The timeline changed after the authoring snapshot.");
    const projectNativeId = text(snapshotRead.privateExecutionIdentity?.nativeProjectId);
    const timelineNativeId = text(snapshotRead.privateExecutionIdentity?.nativeTimelineId);
    if (!projectNativeId || !timelineNativeId) return malformed("CutAgent CLI omitted exact native execution identity from the bracketed timeline snapshot.");
    const context = {
      timelineName: snapshot.timeline.name,
      projectNativeId,
      timelineNativeId,
      frameRate: snapshot.frameRate,
      timelineStartFrame: snapshot.start.value.value,
      sourceNativeId: intent.action === "trim" || intent.action === "remove"
        ? null
        : await resolveMediaPoolNativeIdentity(intent.projectId, intent.source.id, intent.source.snapshotRevision, options),
    };
    let rawPlan;
    try {
      rawPlan = intent.action === "remove" ? null : await resolveService.previewSdkTimelineEdit(intent, context, options);
    } catch (error) {
      if (isLinkedAudioTrimReleaseGate(error, intent)) {
        throw new SdkLiveInspectionError(
          "CAPABILITY_UNAVAILABLE",
          "Linked-audio-preserving trim is not yet available in this CutAgent release.",
        );
      }
      if (intent.action === "insert"
        && error?.name === "BridgeCliError"
        && error?.bridge_error_type === "cutagent_cli_error"
        && error?.cli_error_code === "TIMELINE_CONFLICT"
        && error?.cli_error_details?.reason === "insert_target_not_empty") {
        throw new SdkLiveInspectionError(
          "INVALID_REQUEST",
          "A non-ripple insert requires an unoccupied range on every target track. Choose a free range or preview an overwrite.",
        );
      }
      if (isUnsupportedPartialOverwriteEdge(error, intent)) {
        throw new SdkLiveInspectionError(
          "INVALID_REQUEST",
          "This partial overwrite cannot safely preserve an overlapping clip edge. Replace the whole overlapping clip or remove it before inserting the replacement.",
        );
      }
      if (isUnrepresentableSourceBoundary(error)) {
        throw new SdkLiveInspectionError(
          "INVALID_REQUEST",
          "The requested source-frame boundary cannot be represented exactly at the current timeline rate.",
        );
      }
      if (error?.name === "BridgeCliError"
        && error?.bridge_error_type === "cutagent_cli_error"
        && error?.cli_error_code === "INVALID_TIME_REFERENCE") {
        throw new SdkLiveInspectionError(
          "INVALID_REQUEST",
          "The requested edit time or source range is invalid for the selected media and timeline.",
        );
      }
      throw error;
    }
    const after = (await inspect({ operation: "timeline.snapshot", projectId: intent.projectId, timelineId: intent.timelineId }, options)).value;
    if (after.revision !== snapshot.revision) throw new SdkLiveInspectionError("STALE_REVISION", "The timeline changed while resolving edit impact.");
    return {
      impact: buildTimelineEditImpact(intent, snapshot, rawPlan),
      mutationGuard: snapshotRead.mutationGuard,
      snapshot,
      executionContext: {
        ...context,
        executionRevision: (rawPlan?.payload ?? rawPlan)?.precondition?.revision ?? null,
      },
    };
  };
  const previewTimelineEdit = async (intent, options) => (await prepareTimelineEdit(intent, options)).impact;

  const resolveFairlightPreparedTargets = async (callback, exchangeContext = {}) => {
    const parentRequest = exchangeContext?.originalRequest
      ?? (exchangeContext?.parentMethod === "prepare" ? exchangeContext?.parentPayload?.request : null);
    const phase = callback?.phase;
    if (!parentRequest || !plainObject(callback) || callback.contractVersion !== 1
      || !new Set(["prepare", "current", "verify", "project", "recover"]).has(phase)
      || callback.actionId !== parentRequest.actionId || !Array.isArray(callback.targets)) {
      throw new TypeError("Fairlight live-target resolution requires the exact parent prepare request.");
    }
    const identities = parentRequest.identities;
    const revisions = parentRequest.revisions;
    if (!identities?.projectLibraryId || !identities.projectId || !identities.timelineId
      || !revisions?.projectLibrary || !revisions.project || !revisions.timeline
      || !plainObject(revisions.targets)) {
      throw new TypeError("Fairlight prepared action omitted its exact project and timeline binding.");
    }
    const requestedIds = identities.targetIds;
    if (!Array.isArray(requestedIds) || new Set(requestedIds).size !== requestedIds.length
      || callback.targets.length !== requestedIds.length) {
      throw new TypeError("Fairlight live-target callback changed the signed target set.");
    }
    const callbackById = new Map();
    for (const target of callback.targets) {
      if (!plainObject(target) || typeof target.stableId !== "string"
        || typeof target.revision !== "string" || typeof target.kind !== "string"
        || Object.keys(target).some((key) => !new Set(["kind", "stableId", "revision"]).has(key))
        || callbackById.has(target.stableId)
        || revisions.targets[target.stableId] !== target.revision) {
        throw new TypeError("Fairlight live-target callback changed a signed target identity or revision.");
      }
      callbackById.set(target.stableId, target);
    }
    if (requestedIds.some((stableId) => !callbackById.has(stableId))) {
      throw new TypeError("Fairlight live-target callback omitted a signed target.");
    }

    const projectBefore = await inspect({operation: "project.context"});
    const assertProjectBinding = (projectContext) => {
      const observed = projectContext.value;
      if (projectContext.privateExecutionIdentity?.projectLibraryId !== identities.projectLibraryId
        || observed.project?.id !== identities.projectId
        || observed.timeline?.id !== identities.timelineId
        || observed.projectRevision?.status !== "available"
        || observed.projectRevision.revision !== revisions.project) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The signed Fairlight project-library or project revision changed before target resolution.");
      }
    };
    assertProjectBinding(projectBefore);
    const inspected = await inspect({
      operation: "timeline.snapshot",
      projectId: identities.projectId,
      timelineId: identities.timelineId,
    });
    const projectAfter = await inspect({operation: "project.context"});
    assertProjectBinding(projectAfter);
    if (projectAfter.value.projectRevision.revision !== projectBefore.value.projectRevision.revision) {
      throw new SdkLiveInspectionError("STALE_REVISION", "The Fairlight project context changed during target resolution.");
    }
    const snapshot = inspected.value;
    const preMutationPhase = new Set(["prepare", "current"]).has(phase);
    const privateTargets = exchangeContext?.privateFairlightBinding?.targets;
    if (privateTargets !== undefined
      && (!Array.isArray(privateTargets) || privateTargets.length !== requestedIds.length)) {
      throw new TypeError("Fairlight live-target resolution lacks exact private target custody.");
    }
    if (snapshot.project.id !== identities.projectId || snapshot.timeline.id !== identities.timelineId
      || (preMutationPhase && snapshot.revision !== revisions.timeline)) {
      throw new SdkLiveInspectionError("STALE_REVISION", "The signed Fairlight timeline revision changed before target resolution.");
    }
    const clipRows = snapshot.tracks.flatMap((track) => track.clips.map((clip) => ({track, clip})));
    const rawHandler = callback.handlerResult?.handlerResult;
    const deletingTrack = !preMutationPhase
      && parentRequest.actionId === "cutagent.action.fairlight.delete";
    const reorderingTrack = !preMutationPhase
      && parentRequest.actionId === "cutagent.action.fairlight.track_order.move";
    const movedTrack = reorderingTrack ? rawHandler?.moved_track : null;
    const reorderVerification = reorderingTrack ? rawHandler?.verification : null;
    const reorderSourceIndex = reorderingTrack ? Number(rawHandler?.index) : null;
    const reorderDestinationIndex = reorderingTrack ? Number(rawHandler?.to) : null;
    if (reorderingTrack) {
      const expectedTrackIds = reorderVerification?.expected_track_ids;
      const destinationTrackId = Array.isArray(expectedTrackIds)
        ? expectedTrackIds[reorderDestinationIndex - 1]
        : null;
      if (!plainObject(movedTrack) || typeof movedTrack.track_id !== "string" || !movedTrack.track_id
        || !Number.isInteger(reorderSourceIndex) || !Number.isInteger(reorderDestinationIndex)
        || reorderSourceIndex < 1 || reorderDestinationIndex < 1
        || movedTrack.index !== reorderDestinationIndex
        || reorderVerification?.status !== "verified"
        || movedTrack.track_id !== destinationTrackId) {
        throw new SdkLiveInspectionError(
          "VERIFICATION_FAILED",
          "Fairlight track reorder omitted its verified native track identity and destination.",
        );
      }
    }
    const preparedAudioTracks = callback.prepared?.preState?.snapshot?.tracks;
    const deletedPrivateTrack = deletingTrack
      ? privateTargets?.find((target) => target?.kind === "track")
      : null;
    if (deletingTrack) {
      const currentAudioTrackCount = snapshot.tracks.filter((track) => track.type === "audio").length;
      const preparedTrack = Array.isArray(preparedAudioTracks)
        ? preparedAudioTracks.find((track) => track.index === deletedPrivateTrack?.trackIndex)
        : null;
      if (!plainObject(deletedPrivateTrack) || !plainObject(preparedTrack)
        || preparedTrack.name !== deletedPrivateTrack.trackName
        || currentAudioTrackCount !== preparedAudioTracks.length - 1) {
        throw new SdkLiveInspectionError("VERIFICATION_FAILED", "Fairlight track deletion did not remove the exact signed track.");
      }
    }
    const targetLocator = (target, targetIndex) => {
      const privateTarget = privateTargets?.[targetIndex];
      if (privateTarget !== undefined && (!plainObject(privateTarget) || privateTarget.kind !== target.kind
        || privateTarget.stableId !== target.stableId)) {
        throw new TypeError("Fairlight private target custody changed from the signed target set.");
      }
      if (preMutationPhase && target.revision !== snapshot.revision) {
        throw new SdkLiveInspectionError("STALE_REVISION", "A signed Fairlight target revision is stale.");
      }
      if (target.kind === "project" && target.stableId === snapshot.project.id) {
        return {kind: target.kind, stableId: target.stableId, revision: target.revision, nativeTimelineId: inspected.nativeTimelineId};
      }
      if (target.kind === "timeline" && target.stableId === snapshot.timeline.id) {
        return {kind: target.kind, stableId: target.stableId, revision: target.revision, nativeTimelineId: inspected.nativeTimelineId};
      }
      if (target.kind === "track") {
        if (!preMutationPhase && !plainObject(privateTarget)) {
          throw new TypeError("Fairlight post-mutation track readback lacks exact private target custody.");
        }
        if (deletingTrack && privateTarget === deletedPrivateTrack) {
          return {...privateTarget, kind: target.kind, stableId: target.stableId,
            revision: target.revision, exists: false};
        }
        const expectedTrackIndex = preMutationPhase
          ? null
          : reorderingTrack && privateTarget.trackIndex === reorderSourceIndex
            ? reorderDestinationIndex
            : privateTarget.trackIndex;
        const matches = snapshot.tracks.filter((track) => preMutationPhase
          ? track.snapshotId === target.stableId
          : track.type === privateTarget.trackType && track.index === expectedTrackIndex);
        if (matches.length !== 1) throw new SdkLiveInspectionError(matches.length ? "AMBIGUOUS_TARGET" : "TARGET_NOT_FOUND", "The signed Fairlight track is not one exact live track.");
        const track = matches[0];
        return {kind: target.kind, stableId: target.stableId, revision: target.revision, trackType: track.type, trackIndex: track.index, trackName: track.name};
      }
      if (target.kind === "clip") {
        const matches = clipRows.filter(({clip}) => clip.id === target.stableId);
        if (matches.length === 0 && !preMutationPhase
          && new Set([
            "cutagent.action.fairlight.clip.delete",
            "cutagent.action.fairlight.delete",
          ]).has(parentRequest.actionId)
          && plainObject(privateTarget) && typeof privateTarget.nativeId === "string") {
          return {...privateTarget, kind: target.kind, stableId: target.stableId,
            revision: target.revision, exists: false};
        }
        if (matches.length !== 1) throw new SdkLiveInspectionError(matches.length ? "AMBIGUOUS_TARGET" : "TARGET_NOT_FOUND", "The signed Fairlight clip is not one exact live timeline item.");
        const {track, clip} = matches[0];
        const nativeId = inspected.privateTimelineItemNativeIdByPublicId.get(clip.id);
        if (!nativeId) throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The signed Fairlight clip has no authoritative native identity.");
        return {
          kind: target.kind, stableId: target.stableId, revision: target.revision,
          nativeId, trackType: track.type, trackIndex: track.index, trackName: track.name, clipName: clip.name,
          recordStartFrame: clip.recordRange.start, recordEndFrameExclusive: clip.recordRange.endExclusive,
          sourceStartFrame: clip.sourceRange?.start ?? null, sourceEndFrameExclusive: clip.sourceRange?.endExclusive ?? null,
          sourceFrameRate: clip.sourceFrameRate ?? null,
          sourcePath: inspected.privateTimelineItemSourcePathByPublicId?.get(clip.id) ?? null,
          linkedItemIds: clip.linkedItemIds,
        };
      }
      if (target.kind === "media") {
        const matches = clipRows.filter(({clip}) => clip.mediaPoolItemId === target.stableId);
        if (matches.length !== 1) throw new SdkLiveInspectionError(matches.length ? "AMBIGUOUS_TARGET" : "TARGET_NOT_FOUND", "The signed Fairlight media target is not one exact live placement.");
        const {track, clip} = matches[0];
        return {kind: target.kind, stableId: target.stableId, revision: target.revision, trackType: track.type, trackIndex: track.index, clipName: clip.name, recordStartFrame: clip.recordRange.start};
      }
      if (target.kind === "marker") {
        const matches = snapshot.markers.filter((marker) => marker.id === target.stableId);
        if (matches.length !== 1) throw new SdkLiveInspectionError(matches.length ? "AMBIGUOUS_TARGET" : "TARGET_NOT_FOUND", "The signed Fairlight marker is not one exact live marker.");
        return {kind: target.kind, stableId: target.stableId, revision: target.revision, recordFrame: matches[0].position.value.value};
      }
      throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The signed Fairlight target kind is unavailable in the exact live snapshot.");
    };
    const targets = requestedIds.map((stableId, index) => targetLocator(callbackById.get(stableId), index));
    const normalizedInput = plainObject(callback.normalizedInput)
      ? callback.normalizedInput
      : callback.prepared?.lowering?.normalizedInput;
    let handlerOverrides = {};
    if (new Set([
      "cutagent.action.fairlight.ai.voice_isolation",
      "cutagent.action.fairlight.eq.set",
    ]).has(parentRequest.actionId)) {
      const clipTargets = targets.filter((target) => target.kind === "clip" && target.trackType === "audio");
      if (targets.length !== 1 || clipTargets.length !== 1
        || typeof clipTargets[0].nativeId !== "string" || !clipTargets[0].nativeId) {
        throw new SdkLiveInspectionError(
          "STALE_REVISION",
          "Fairlight clip processing requires one exact signed native audio clip.",
        );
      }
      handlerOverrides = parentRequest.actionId === "cutagent.action.fairlight.eq.set"
        ? {...handlerOverrides, sdk_audio_item_id: clipTargets[0].nativeId}
        : {...handlerOverrides, sdk_native_clip_id: clipTargets[0].nativeId};
    }
    if (new Set([
      "cutagent.action.fairlight.dynamics.disable",
      "cutagent.action.fairlight.dynamics.enable",
      "cutagent.action.fairlight.dynamics.set",
    ]).has(parentRequest.actionId)) {
      const trackTargets = targets.filter((target) => target.kind === "track" && target.trackType === "audio");
      if (targets.length !== 1 || trackTargets.length !== 1
        || !Number.isInteger(trackTargets[0].trackIndex) || trackTargets[0].trackIndex < 1) {
        throw new SdkLiveInspectionError(
          "STALE_REVISION",
          "Fairlight dynamics requires one exact signed audio track.",
        );
      }
      if (normalizedInput?.track !== undefined && normalizedInput.track !== trackTargets[0].trackIndex) {
        throw new SdkLiveInspectionError(
          "STALE_REVISION",
          "Fairlight dynamics input disagrees with the exact signed audio track.",
        );
      }
      handlerOverrides = {...handlerOverrides, track: trackTargets[0].trackIndex};
    }
    if (parentRequest.actionId === "cutagent.action.sdk.fairlight.plan.apply"
      && Array.isArray(normalizedInput?.changes)) {
      const loudness = normalizedInput.changes.filter((change) => change?.kind === "loudness"
        && change?.target?.kind === "track");
      if (loudness.length) {
        const seen = new Set();
        const trackLoudness = loudness.map((change) => {
          const trackIndex = change.target.trackIndex;
          if (!Number.isInteger(trackIndex) || trackIndex < 1 || seen.has(trackIndex)) {
            throw new SdkLiveInspectionError(
              "INVALID_REQUEST",
              "Track loudness requires distinct exact one-based track targets.",
            );
          }
          seen.add(trackIndex);
          const track = snapshot.tracks.find((candidate) => candidate.type === "audio" && candidate.index === trackIndex);
          const clips = track?.clips;
          const readback = inspected.privateFairlightPlanReadback?.tracks
            ?.find((candidate) => candidate.trackIndex === trackIndex);
          if (!track || !Array.isArray(clips) || clips.length < 1 || clips.length > 4096
            || !Number.isFinite(readback?.levelDb)
            || clips.some((clip) => typeof clip.id !== "string" || !clip.id
              || !Number.isSafeInteger(clip.recordRange?.start)
              || !Number.isSafeInteger(clip.recordRange?.endExclusive)
              || clip.recordRange.endExclusive <= clip.recordRange.start)) {
            throw new SdkLiveInspectionError(
              "CAPABILITY_NEGOTIATION_FAILED",
              "Track loudness requires complete durable clip and range closure.",
            );
          }
          const ranges = clips.map((clip) => ({
            clipId: clip.id,
            startFrame: clip.recordRange.start,
            endExclusiveFrame: clip.recordRange.endExclusive,
          })).sort((left, right) => left.startFrame - right.startFrame
            || left.endExclusiveFrame - right.endExclusiveFrame
            || left.clipId.localeCompare(right.clipId));
          return {
            trackIndex,
            currentFaderDb: readback.levelDb,
            startFrame: Math.min(...ranges.map((row) => row.startFrame)),
            endExclusiveFrame: Math.max(...ranges.map((row) => row.endExclusiveFrame)),
            clipIds: ranges.map((row) => row.clipId),
            rangeDigest: privateTextDigest(JSON.stringify(canonicalize({trackIndex, ranges}))),
          };
        });
        handlerOverrides = {...handlerOverrides, trackLoudness};
      }
    }
    if (new Set([
      "cutagent.action.fairlight.automation.write",
      "cutagent.action.fairlight.mixer.fader",
    ]).has(parentRequest.actionId)
      && typeof normalizedInput?.bus === "string" && normalizedInput.bus) {
      const buses = snapshot.fairlight?.buses?.buses;
      const matches = Array.isArray(buses)
        ? buses.filter((bus) => plainObject(bus) && bus.name === normalizedInput.bus)
        : [];
      if (targets.length !== 1 || targets[0].kind !== "timeline" || matches.length !== 1) {
        throw new SdkLiveInspectionError(
          matches.length > 1 ? "AMBIGUOUS_TARGET" : "TARGET_NOT_FOUND",
          "The signed Fairlight automation bus is not one exact live bus.",
        );
      }
      handlerOverrides = {bus: matches[0].name};
    }
    if (parentRequest.actionId === "cutagent.action.fairlight.mixer.pan") {
      const [target] = targets;
      const privateTrackRows = inspected.privateFairlightPlanReadback?.tracks;
      const privateTrack = Array.isArray(privateTrackRows)
        ? privateTrackRows.filter((row) => row?.trackIndex === target?.trackIndex)
        : [];
      if (targets.length !== 1 || target?.kind !== "track" || target.trackType !== "audio"
        || privateTrack.length !== 1 || privateTrack[0].panWritable !== true) {
        throw new SdkLiveInspectionError(
          "CAPABILITY_NEGOTIATION_FAILED",
          "Fairlight mixer pan requires one exact mono audio track with authoritative pan-write support.",
        );
      }
    }
    const fairlightReadbackRequest = () => {
      const actionId = parentRequest.actionId;
      const clip = targets.find((target) => target.kind === "clip");
      const track = targets.find((target) => target.kind === "track");
      if (/^cutagent\.action\.fairlight\.(?:ai\.)/u.test(actionId)) {
        return {actionId: "cutagent.action.fairlight.ai.read", input: {clip: clip?.nativeId}};
      }
      if (actionId === "cutagent.action.fairlight.channel_map.set") {
        return {actionId: "cutagent.action.fairlight.channel_map.clip", input: {clipName: clip?.nativeId}};
      }
      if (/^cutagent\.action\.fairlight\.dynamics\./u.test(actionId)) {
        return {actionId: "cutagent.action.fairlight.dynamics.read", input: {track: handlerOverrides.track}};
      }
      if (new Set([
        "cutagent.action.fairlight.effect.add",
        "cutagent.action.fairlight.effect.remove",
        "cutagent.action.fairlight.effect.set_param",
        "cutagent.action.fairlight.transition.add",
      ]).has(actionId)) {
        if (new Set([
          "cutagent.action.fairlight.effect.add",
          "cutagent.action.fairlight.effect.remove",
        ]).has(actionId) && !normalizedInput?.clip) {
          const effect = String(normalizedInput?.effect ?? "").trim().toLowerCase().replaceAll(/[_-]/gu, " ");
          return effect === "eq" || effect === "equalizer" || effect === "equaliser"
            ? {actionId: "cutagent.action.fairlight.eq.read", input: {}}
            : {actionId: "cutagent.action.fairlight.dynamics.read", input: {}};
        }
        const effect = String(normalizedInput?.effect ?? "").trim().toLowerCase().replaceAll(/[_-]/gu, " ");
        return effect === "voice isolation"
          ? {actionId: "cutagent.action.fairlight.ai.read", input: {clip: clip?.nativeId}}
          : {actionId: "cutagent.action.fairlight.effect.list", input: {clip: clip?.nativeId}};
      }
      if (/^cutagent\.action\.fairlight\.elastic\./u.test(actionId)) {
        return {actionId: "cutagent.action.fairlight.elastic.info", input: {limit: 4096}};
      }
      if (actionId === "cutagent.action.fairlight.eq.set") {
        return null;
      }
      if (new Set([
        "cutagent.action.fairlight.lock",
        "cutagent.action.fairlight.mute",
        "cutagent.action.fairlight.rename",
        "cutagent.action.fairlight.solo_restore",
        "cutagent.action.fairlight.unlock",
        "cutagent.action.fairlight.unmute",
      ]).has(actionId)) {
        return null;
      }
      if (actionId === "cutagent.action.fairlight.automation.write") {
        if (phase !== "verify") return null;
        return normalizedInput?.bus
          ? {actionId: "cutagent.action.fairlight.mixer.read", input: {bus: handlerOverrides.bus}}
          : null;
      }
      if (actionId === "cutagent.action.fairlight.voice_isolation.set") {
        return {actionId: "cutagent.action.fairlight.voice_isolation.get", input: {track: track?.trackIndex}};
      }
      if (new Set([
        "cutagent.action.fairlight.bus.level",
        "cutagent.action.fairlight.mixer.fader",
        "cutagent.action.fairlight.mixer.pan",
      ]).has(actionId)) {
        return {actionId: "cutagent.action.fairlight.mixer.read", input: normalizedInput?.bus
          ? {bus: handlerOverrides.bus}
          : {track: track?.trackIndex}};
      }
      if (actionId.startsWith("cutagent.action.fairlight.")
        && !actionId.includes("sound_library")
        && !actionId.includes("bounce")
        && actionId !== "cutagent.action.fairlight.export.audio") {
        return {actionId: "cutagent.action.fairlight.tracks", input: {}};
      }
      return null;
    };
    const readbackRequest = fairlightReadbackRequest();
    let actionReadback = parentRequest.actionId === "cutagent.action.sdk.fairlight.plan.apply"
      ? inspected.privateFairlightPlanReadback
      : readbackRequest && typeof resolveService.executeSdkLowLevelAction === "function"
        ? await resolveService.executeSdkLowLevelAction(readbackRequest, {carrier: "sdk"})
        : null;
    if (parentRequest.actionId === "cutagent.action.fairlight.voice_isolation.set") {
      const [target] = targets;
      const amount = finiteNumber(actionReadback?.amount);
      if (targets.length !== 1 || target?.kind !== "track"
        || !plainObject(actionReadback)
        || actionReadback.track !== target.trackIndex
        || typeof actionReadback.isEnabled !== "boolean"
        || amount === null || amount < 0 || amount > 100) {
        throw new SdkLiveInspectionError(
          "INVALID_RESPONSE",
          "Fairlight track Voice Isolation readback is unavailable or disagrees with the signed track.",
        );
      }
      actionReadback = {
        isEnabled: actionReadback.isEnabled,
        amount,
        track: target.trackIndex,
        tracks: [{index: target.trackIndex, name: target.trackName, type: "audio"}],
      };
    }
    if (phase === "verify" && parentRequest.actionId === "cutagent.action.fairlight.eq.set") {
      const [target] = targets;
      if (targets.length !== 1 || target?.kind !== "clip"
        || rawHandler?.audio_item_id !== target.nativeId
        || rawHandler?.verification?.status !== "verified") {
        throw new SdkLiveInspectionError(
          "VERIFICATION_FAILED",
          "Fairlight EQ readback did not prove the exact signed audio clip.",
        );
      }
      actionReadback = {
        audioItemId: target.nativeId,
        clipName: target.clipName,
        bandCount: rawHandler.band_count,
        bands: rawHandler.bands,
      };
    }
    if (new Set([
      "cutagent.action.fairlight.mixer.fader",
      "cutagent.action.fairlight.mixer.pan",
    ]).has(parentRequest.actionId) && !normalizedInput?.bus) {
      const [target] = targets;
      const readbackTrack = actionReadback?.track;
      const fader = actionReadback?.mixer?.fader;
      const mixerPan = actionReadback?.mixer?.pan;
      const privateTrackRows = inspected.privateFairlightPlanReadback?.tracks;
      const privateTrack = Array.isArray(privateTrackRows)
        ? privateTrackRows.filter((row) => row?.trackIndex === target?.trackIndex)
        : [];
      const levelDb = finiteNumber(fader?.level_db);
      const nativePanPercent = finiteNumber(mixerPan?.pan);
      const privatePan = finiteNumber(privateTrack[0]?.pan);
      const pan = nativePanPercent === null ? privatePan : nativePanPercent / 100;
      if (targets.length !== 1 || target?.kind !== "track"
        || !plainObject(readbackTrack) || readbackTrack.index !== target.trackIndex
        || (readbackTrack.name !== "" && readbackTrack.name !== target.trackName)
        || typeof readbackTrack.format !== "string" || !readbackTrack.format
        || typeof readbackTrack.enabled !== "boolean" || typeof readbackTrack.locked !== "boolean"
        || levelDb === null || privateTrack.length !== 1 || pan === null
        || Math.abs(pan) > 1 || privatePan === null || Math.abs(privatePan - pan) > 1e-9
        || finiteNumber(privateTrack[0].levelDb) !== levelDb) {
        throw new SdkLiveInspectionError(
          "INVALID_RESPONSE",
          "Fairlight track mixer readback is unavailable or disagrees with the signed track.",
        );
      }
      actionReadback = {
        tracks: [{
          index: readbackTrack.index,
          name: target.trackName,
          type: readbackTrack.format,
          enabled: readbackTrack.enabled,
          locked: readbackTrack.locked,
        }],
        level_db: levelDb,
        pan,
        angle: null,
        spread: null,
      };
    }
    if (new Set([
      "cutagent.action.fairlight.dynamics.disable",
      "cutagent.action.fairlight.dynamics.enable",
      "cutagent.action.fairlight.dynamics.set",
    ]).has(parentRequest.actionId)) {
      const [target] = targets;
      const readbackTrack = actionReadback?.track;
      const processorFields = [
        "comp_enable", "comp_threshold", "comp_ratio",
        "gate_enable", "gate_threshold",
        "limiter_enable", "limiter_threshold",
      ];
      if (targets.length !== 1 || target?.kind !== "track"
        || actionReadback?.status !== "ok"
        || !plainObject(readbackTrack) || readbackTrack.index !== target.trackIndex
        || (readbackTrack.name !== "" && readbackTrack.name !== target.trackName)
        || typeof readbackTrack.format !== "string" || !readbackTrack.format
        || typeof readbackTrack.track_id !== "string" || !readbackTrack.track_id
        || typeof actionReadback.sequence_id !== "string" || !actionReadback.sequence_id
        || processorFields.some((field) => field.endsWith("_enable")
          ? typeof actionReadback[field] !== "boolean"
          : finiteNumber(actionReadback[field]) === null)) {
        throw new SdkLiveInspectionError(
          "INVALID_RESPONSE",
          "Fairlight dynamics readback is unavailable or disagrees with the signed track.",
        );
      }
      actionReadback = {
        tracks: [{
          index: readbackTrack.index,
          name: target.trackName,
          type: readbackTrack.format,
        }],
        ...Object.fromEntries(processorFields.map((field) => [field, actionReadback[field]])),
      };
    }
    if (phase === "verify" && parentRequest.actionId === "cutagent.action.fairlight.automation.write") {
      const requestedValue = finiteNumber(normalizedInput?.value);
      const [target] = targets;
      const frame = integer(rawHandler?.requested_record_frame);
      const itemId = text(rawHandler?.item_id);
      const keyframes = Array.isArray(rawHandler?.verification?.keyframes)
        ? rawHandler.verification.keyframes
        : [];
      const exactPoint = keyframes.filter((point) => (
        integer(point?.frame) === frame && finiteNumber(point?.value) === requestedValue
      ));
      if (targets.length !== 1 || target?.kind !== "track"
        || target.trackIndex !== integer(normalizedInput?.track)
        || requestedValue === null || frame === null || !itemId
        || rawHandler?.automation_owner !== "audio_clip"
        || rawHandler?.verification?.status !== "verified"
        || exactPoint.length !== 1) {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "Fairlight automation lacks exact post-reopen audio-clip envelope readback.");
      }
      actionReadback = {
        targetKind: "track", record_frame: frame, value: requestedValue, mode: "volume",
        tracks: [{index: target.trackIndex, name: target.trackName, type: "audio"}],
      };
    }
    if (phase === "verify" && parentRequest.actionId === "cutagent.action.fairlight.mixer.fader"
      && normalizedInput?.bus) {
      const mixer = actionReadback?.mixer;
      const mixerTarget = mixer?.target;
      if (!plainObject(mixer) || !plainObject(mixerTarget)
        || typeof handlerOverrides.bus !== "string"
        || mixerTarget.busName !== handlerOverrides.bus
        || mixerTarget.busKind !== "main") {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "Fairlight bus fader readback is unavailable.");
      }
      actionReadback = {
        targetKind: "bus",
        bus: mixerTarget.busName,
        busKind: mixerTarget.busKind,
        level_db: mixer.levelDb,
        pan: mixer.pan,
        angle: mixer.angle,
        spread: mixer.spread,
      };
    }
    const splitSegments = phase === "verify"
      && parentRequest.actionId === "cutagent.action.fairlight.clip.split"
      && Array.isArray(rawHandler?.segments)
      ? rawHandler.segments.map((segment) => {
          const nativeId = text(segment?.item_id);
          const publicEntry = [...inspected.privateTimelineItemNativeIdByPublicId.entries()]
            .find(([, candidateNativeId]) => candidateNativeId === nativeId);
          const publicId = publicEntry?.[0];
          const match = clipRows.find(({clip}) => clip.id === publicId);
          if (!publicId || !match || match.track.type !== "audio") {
            throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "A verified Fairlight split segment has no exact live identity.");
          }
          return {
            stableId: publicId, trackIndex: match.track.index, clipName: match.clip.name,
            recordStartFrame: match.clip.recordRange.start,
            recordEndFrameExclusive: match.clip.recordRange.endExclusive,
            sourceStartFrame: match.clip.sourceRange?.start ?? null,
            sourceEndFrameExclusive: match.clip.sourceRange?.endExclusive ?? null,
          };
        })
      : null;
    const createdSplitIds = new Set(splitSegments?.map((segment) => segment.stableId) ?? []);
    const protectedStateDigest = privateTextDigest(JSON.stringify(canonicalize({
      project: snapshot.project, timeline: snapshot.timeline, revision: snapshot.revision,
      targetIds: requestedIds, mutationGuard: inspected.mutationGuard,
    })));
    const changesOrRemovesTargetLinkTopology = new Set([
      "cutagent.action.fairlight.delete",
      "cutagent.action.fairlight.clip.delete",
      "cutagent.action.fairlight.clip.link",
      "cutagent.action.fairlight.clip.split",
      "cutagent.action.fairlight.clip.unlink",
    ]).has(parentRequest.actionId);
    const protectedTrackIndex = (track) => {
      if (!reorderingTrack || track.type !== "audio") return track.index;
      if (reorderSourceIndex < reorderDestinationIndex
        && track.index >= reorderSourceIndex && track.index < reorderDestinationIndex) {
        return track.index + 1;
      }
      if (reorderSourceIndex > reorderDestinationIndex
        && track.index > reorderDestinationIndex && track.index <= reorderSourceIndex) {
        return track.index - 1;
      }
      return track.index;
    };
    const currentProtectedState = {
      linkedTopologyDigest: privateTextDigest(JSON.stringify(canonicalize(clipRows
        .filter(({track, clip}) => !(changesOrRemovesTargetLinkTopology
          && targets.some((target) => target.kind === "clip" && target.stableId === clip.id))
          && !(targets.some((target) => target.kind === "track" && target.trackIndex === track.index)
            && (!deletingTrack || preMutationPhase))
          && !createdSplitIds.has(clip.id))
        .map(({clip}) => ({id: clip.id, linkedItemIds: clip.linkedItemIds}))))),
      unrelatedTracksDigest: privateTextDigest(JSON.stringify(canonicalize(snapshot.tracks
        .filter((track) => !(targets.some((target) => target.kind === "track"
          && target.trackIndex === track.index && target.trackType === track.type)
          && (!deletingTrack || preMutationPhase)))
        .map((track) => ({
          timelineId: track.timelineId,
          type: track.type,
          index: deletingTrack && track.type === "audio"
            && track.index >= deletedPrivateTrack.trackIndex
            ? track.index + 1
            : protectedTrackIndex(track),
          name: track.name,
          enabled: track.enabled,
          locked: track.locked,
          clips: track.clips.filter((clip) => !targets.some((target) => target.kind === "clip"
            && target.stableId === clip.id) && !createdSplitIds.has(clip.id)).map((clip) => ({
              id: clip.id,
              name: clip.name,
              recordRange: clip.recordRange,
              duration: clip.duration,
              sourceRange: clip.sourceRange,
              mediaPoolItemId: clip.mediaPoolItemId,
              linkedItemIds: clip.linkedItemIds,
            })),
        }))))),
      snapshotDigest: protectedStateDigest,
    };
    const response = {
      contractVersion: 1,
      actionId: parentRequest.actionId,
      phase,
      scope: {
        projectLibraryId: identities.projectLibraryId,
        projectId: identities.projectId,
        timelineId: identities.timelineId,
        projectLibraryRevision: revisions.projectLibrary,
        projectRevision: revisions.project,
        timelineRevision: revisions.timeline,
      },
      snapshot: {
        revision: snapshot.revision,
        frameRate: snapshot.frameRate,
        digest: protectedStateDigest,
        tracks: snapshot.tracks
          .filter((track) => track.type === "audio")
          .map((track) => ({
            index: track.index,
            name: track.name,
            enabled: track.enabled,
            locked: track.locked,
            format: track.type,
          })),
        audioRanges: clipRows
          .filter(({track, clip}) => track.type === "audio" && (
            targets.some((target) => target.kind === "clip")
              ? targets.some((target) => target.kind === "clip" && target.stableId === clip.id)
              : targets.some((target) => target.kind === "project" || target.kind === "timeline")
                || targets.some((target) => target.kind === "track" && target.trackIndex === track.index)
          ))
          .slice(0, 4096)
          .map(({track, clip}) => ({
            clipId: clip.id,
            trackIndex: track.index,
            startFrame: clip.recordRange.start,
            endExclusiveFrame: clip.recordRange.endExclusive,
          })),
        ...(actionReadback === null ? {} : {actionReadback}),
      },
      protectedState: currentProtectedState,
      handlerOverrides,
      targets: targets.map((target) => ({...target, exists: target.exists ?? true})),
    };
    if (phase === "verify" && parentRequest.actionId === "cutagent.action.fairlight.clip.split") {
      if (!splitSegments?.length) {
        throw new SdkLiveInspectionError("INVALID_RESPONSE", "Fairlight clip split omitted its verified segment identities.");
      }
      response.createdSegments = splitSegments;
    }
    if (parentRequest.actionId === "cutagent.action.fairlight.delete"
      && new Set(["prepare", "current"]).has(phase)) {
      const [trackTarget, ...clipTargets] = targets;
      const liveTrack = trackTarget?.kind === "track"
        ? snapshot.tracks.find((track) => track.snapshotId === trackTarget.stableId)
        : null;
      const liveClipIds = liveTrack?.clips.map((clip) => clip.id) ?? null;
      if (!liveTrack
        || JSON.stringify(clipTargets.map((target) => target.stableId)) !== JSON.stringify(liveClipIds)) {
        throw new SdkLiveInspectionError(
          "STALE_REVISION",
          "Fairlight track deletion lacks an exhaustive live clip closure.",
        );
      }
      response.impactClosure = {
        kind: "track_delete",
        complete: true,
        trackId: trackTarget.stableId,
        clipIds: liveClipIds,
        digest: privateTextDigest(JSON.stringify(canonicalize({
          trackId: trackTarget.stableId,
          clipIds: liveClipIds,
          timelineRevision: snapshot.revision,
        }))),
      };
    }
    if (phase === "verify") {
      const beforeProtected = callback.protectedState;
      response.protectedStatePreserved = plainObject(beforeProtected)
        && beforeProtected.linkedTopologyDigest === currentProtectedState.linkedTopologyDigest
        && beforeProtected.unrelatedTracksDigest === currentProtectedState.unrelatedTracksDigest;
      response.outcome = response.protectedStatePreserved ? "passed" : "failed";
      response.evidence = [{
        modality: "readback",
        digest: privateTextDigest(JSON.stringify(canonicalize({protectedStateDigest, targets, actionReadback}))),
        summary: response.protectedStatePreserved
          ? "Fresh bracketed Fairlight readback preserved linked topology and unrelated tracks."
          : "Fresh bracketed Fairlight readback did not preserve linked topology and unrelated tracks.",
      }];
      response.currentReadback = actionReadback ?? {tracks: response.snapshot.tracks};
      response.beforeReadback = callback.prepared?.preState?.snapshot?.actionReadback
        ?? (callback.prepared?.preState?.snapshot?.tracks
          ? {tracks: callback.prepared.preState.snapshot.tracks}
          : null);
    }
    if (phase === "recover") {
      response.recovery = {outcome: "manual_required", attempted: true, manualActionRequired: true};
    }
    // Project intentionally fails closed until an action-specific live readback
    // authority can produce that action's exact public result schema.
    return Object.freeze(response);
  };
  return {
    async read(request, options = {}) { return (await inspect(request, options)).value; },
    async readProjectInventory(options = {}) {
      const before = await inspect({ operation: "project.folder_context" }, options);
      const rows = await resolveService.listProjects({ ...options, strictSdkInventory: true });
      const after = await inspect({ operation: "project.folder_context" }, options);
      if (!Array.isArray(rows) || rows.length > 1_024) {
        return malformed("CutAgent CLI returned an invalid or unbounded project inventory.");
      }
      if (before.mutationGuard !== after.mutationGuard
        || JSON.stringify(canonicalize(before.value)) !== JSON.stringify(canonicalize(after.value))) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The project context changed while CutAgent was reading its project inventory.");
      }
      if (before.privateExecutionIdentity.projectLibraryId === null) {
        return malformed("CutAgent CLI omitted the exact project-library ownership scope.");
      }
      const projectFolder = before.privateExecutionIdentity.nativeProjectFolder;
      if (!projectFolder || !projectFolder.nativeId || !projectFolder.path) {
        return malformed("CutAgent CLI omitted the exact project-folder ownership scope.");
      }
      if (!Array.isArray(projectFolder.projectRecords)
        || projectFolder.projectRecords.length !== projectFolder.projects.length) {
        return malformed("CutAgent CLI omitted the exact native project identities.");
      }
      const projectRecords = new Map();
      const nativeProjectIds = new Set();
      for (const record of projectFolder.projectRecords) {
        if (!record?.name || !record.nativeId || projectRecords.has(record.name)
          || nativeProjectIds.has(record.nativeId)) {
          return malformed("CutAgent CLI returned incomplete or ambiguous native project identities.");
        }
        projectRecords.set(record.name, record.nativeId);
        nativeProjectIds.add(record.nativeId);
      }
      const names = new Set();
      let currentCount = 0;
      const projects = rows.map((row, offset) => {
        const name = text(row?.name);
        if (!name || names.has(name)) {
          throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned an incomplete or ambiguous project identity.");
        }
        names.add(name);
        const nativeId = projectRecords.get(name);
        if (!nativeId) {
          return malformed("CutAgent CLI project rows did not match the native project inventory.");
        }
        const current = row?.current === true
          && projectFolder.openProjectNativeId !== null
          && projectFolder.openProjectNativeId === before.privateExecutionIdentity.nativeProjectId;
        if (current) currentCount += 1;
        const index = Number.isSafeInteger(row?.index) && row.index >= 1 ? row.index : offset + 1;
        return {
          current,
          index,
          project: {
            id: digest("project_", { identityNamespace: stableIdentityNamespace, nativeId }),
            name,
          },
        };
      });
      const folderProjects = [...projectFolder.projects].sort();
      const returnedProjects = [...names].sort();
      if (JSON.stringify(folderProjects) !== JSON.stringify(returnedProjects)) {
        return malformed("CutAgent CLI project rows did not match the complete bracketed project-folder inventory.");
      }
      if (currentCount > 1) {
        return malformed("CutAgent CLI returned more than one active project within its project inventory.");
      }
      if (currentCount === 1 && (
        before.value.project === null
        || !projects.some((row) => row.current
          && row.project.name === before.value.project.name
          && row.project.id === before.value.project.id)
      )) {
        return malformed("CutAgent CLI did not bind the active project within its project inventory.");
      }
      if (new Set(projects.map((row) => row.index)).size !== projects.length) {
        throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned ambiguous project indexes.");
      }
      return Object.freeze(projects);
    },
    async readProjectFolderInventory(options = {}) {
      const inspected = await inspect({ operation: "project.folder_context" }, options);
      const projectLibraryId = inspected.privateExecutionIdentity?.projectLibraryId;
      const folder = inspected.privateExecutionIdentity?.nativeProjectFolder;
      if (typeof projectLibraryId !== "string" || !projectLibraryId
        || !folder || typeof folder.path !== "string" || !folder.path
        || typeof folder.nativeId !== "string" || !folder.nativeId
        || !Array.isArray(folder.children) || folder.children.length > 1_024
        || !Array.isArray(folder.projects) || folder.projects.length > 1_024) {
        return malformed("CutAgent CLI omitted the exact project-folder ownership scope.");
      }
      const folderId = (path) => opaque("project_folder_", `${projectLibraryId}:${path}`);
      const currentParts = folder.path.split(" / ");
      const currentName = currentParts.at(-1);
      const seenPaths = new Set();
      const seenNativeIds = new Set();
      const children = folder.children.map((child) => {
        const name = text(child?.name);
        const path = text(child?.path);
        const nativeId = text(child?.nativeId);
        if (!name || !path || !nativeId || path !== `${folder.path} / ${name}`
          || seenPaths.has(path) || seenNativeIds.has(nativeId)) {
          throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "DaVinci Resolve returned an incomplete or ambiguous project-folder inventory.");
        }
        seenPaths.add(path);
        seenNativeIds.add(nativeId);
        return Object.freeze({id: folderId(path), name, path});
      }).sort((left, right) => Buffer.compare(Buffer.from(left.path, "utf8"), Buffer.from(right.path, "utf8")));
      const projectNames = folder.projects.map(text);
      if (!currentName || seenNativeIds.has(folder.nativeId)
        || projectNames.some((name) => !name) || new Set(projectNames).size !== projectNames.length) {
        return malformed("CutAgent CLI returned an invalid project-folder inventory.");
      }
      return Object.freeze({
        folder: Object.freeze({id: folderId(folder.path), name: currentName, path: folder.path}),
        folders: Object.freeze(children),
        projects: Object.freeze(projectNames.sort((left, right) => Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8")))),
      });
    },
    resolveMediaPoolPrivateAsset,
    resolveMediaPoolPrivateFolder,
    captureManagedTimelineAssets,
    async readCurrentTimelineBinding(request, options = {}) {
      if (request.operation !== "timeline.current") {
        throw new TypeError("Current Timeline binding requires timeline.current.");
      }
      const inspected = await inspect(request, options);
      const nativeProjectId = text(inspected.privateExecutionIdentity?.nativeProjectId);
      const nativeTimelineId = text(inspected.privateExecutionIdentity?.nativeTimelineId);
      if (!nativeProjectId || !nativeTimelineId) {
        return malformed("CutAgent CLI omitted the exact native current Timeline binding.");
      }
      return inspected;
    },
    resolveFairlightPreparedTargets,
    async readWithMutationGuard(request, options = {}) {
      if (!["project.context", "project.folder_context", "project.library_context", "mediaPool.page", "timeline.snapshot", "color.current"].includes(request.operation)) throw new TypeError("Mutation guards require a project, Media Pool, timeline, or Color snapshot.");
      const inspected = await inspect(request, options);
      if (typeof inspected.mutationGuard !== "string") return malformed("CutAgent CLI omitted the exact mutation guard.");
      return inspected;
    },
    async previewTimelineEdit(intent, options = {}) { return previewTimelineEdit(intent, options); },
    async prepareTimelineEdit(intent, options = {}) { return prepareTimelineEdit(intent, options); },
    async prepareMulticamCreate(input, options = {}) {
      const project = (await inspect({ operation: "project.current" }, options)).value;
      if (project.id !== input.projectId) throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed after multicam authoring.");
      const sources = [];
      for (const source of input.sources) {
        const asset = await resolveMediaPoolPrivateAsset(input.projectId, source.mediaPoolItemId, input.mediaPoolRevision, options);
        if (asset.kind !== "video") throw new SdkLiveInspectionError("CAPABILITY_UNAVAILABLE", "Standard multicam creation requires video source assets.");
        if (!asset.sourcePath) throw new SdkLiveInspectionError("CAPABILITY_UNAVAILABLE", "The exact local source path is unavailable for this multicam asset.");
        sources.push(Object.freeze({ ...asset, mediaPoolItemId: source.mediaPoolItemId, angleLabel: source.angleLabel }));
      }
      return Object.freeze({ project, sources: Object.freeze(sources), mediaPoolRevision: input.mediaPoolRevision });
    },
    async resolvePreparedTimelineMedia(input, options = {}) {
      if (!input || typeof input.projectId !== "string" || !Array.isArray(input.mediaPoolItemIds)
        || input.mediaPoolItemIds.length === 0
        || new Set(input.mediaPoolItemIds).size !== input.mediaPoolItemIds.length) {
        throw new TypeError("Prepared Timeline media resolution requires unique exact Media Pool identities.");
      }
      const project = (await inspect({operation: "project.current"}, options)).value;
      if (project.id !== input.projectId) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed before Timeline media resolution.");
      }
      const values = [];
      let mediaPoolRevision = null;
      for (const mediaPoolItemId of input.mediaPoolItemIds) {
        const asset = await resolveMediaPoolPrivateAsset(
          input.projectId, mediaPoolItemId, mediaPoolRevision, options,
        );
        if (typeof asset.nativeId !== "string" || !asset.nativeId) {
          throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "A prepared Timeline Media Pool target lost exact native identity.");
        }
        mediaPoolRevision ??= asset.revision;
        values.push(Object.freeze({
          mediaPoolItemId,
          nativeId: asset.nativeId,
          revision: asset.revision,
          poolDigest: asset.poolDigest,
          name: asset.name,
          kind: asset.kind,
          sourcePath: asset.sourcePath ?? null,
        }));
      }
      return Object.freeze(values);
    },
    async prepareMulticamTimelineMutation(input, options = {}) {
      const timelineInspection = await inspect({ operation: "timeline.current", projectId: input.projectId }, options);
      const timeline = timelineInspection.value;
      if (timeline.id !== input.timelineId) throw new SdkLiveInspectionError("STALE_REVISION", "The active timeline changed after multicam authoring.");
      const timelineRead = await inspect({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, options);
      if (timelineRead.value.revision !== input.timelineRevision) throw new SdkLiveInspectionError("STALE_REVISION", "The timeline changed after multicam authoring.");
      const timelineNativeId = text(timelineInspection.privateExecutionIdentity?.nativeTimelineId);
      if (!timelineNativeId || timelineRead.nativeTimelineId !== timelineNativeId) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The exact native timeline identity changed during multicam preparation.");
      }
      const multicam = await resolveMulticamPrivateTarget(input.projectId, input.multicamId, input.multicamRevision, options);
      const isSwitch = Array.isArray(input.switches);
      if (isSwitch && multicam.value.angles.some((angle) => angle.sources.length !== 1)) {
        throw new SdkLiveInspectionError(
          "CAPABILITY_UNAVAILABLE",
          "SDK multicam timeline mutation currently requires exactly one source clip per angle.",
        );
      }
      const sources = [];
      for (const angle of multicam.value.angles) {
        for (const source of angle.sources) {
          const asset = await resolveMediaPoolPrivateAsset(input.projectId, source.mediaPoolItemId, null, options);
          if (!asset.sourcePath) throw new SdkLiveInspectionError("CAPABILITY_UNAVAILABLE", "The exact local source path is unavailable for this multicam source.");
          sources.push(Object.freeze({ ...asset, mediaPoolItemId: source.mediaPoolItemId, angleLabel: angle.label }));
        }
      }
      if (isSwitch && new Set(sources.map((source) => source.name)).size !== sources.length) {
        throw new SdkLiveInspectionError(
          "CAPABILITY_UNAVAILABLE",
          "SDK multicam timeline mutation requires unique source clip names until source-ID-bound switch lowering is available.",
        );
      }
      let endFrame = Math.max(
        timelineRead.value.start.value.value + 1,
        ...timelineRead.value.tracks.flatMap((track) => track.clips.map((clip) => clip.recordRange.endExclusive)),
      );
      if (isSwitch) {
        const scope = input.switches[0]?.scope;
        const affectedTypes = scope === "video" ? ["video"] : scope === "audio" ? ["audio"] : ["video", "audio"];
        const targetRanges = [];
        for (const trackType of affectedTypes) {
          const populated = timelineRead.value.tracks.filter((track) => track.type === trackType && track.clips.length > 0);
          if (populated.length !== 1 || populated[0].index !== 1) {
            throw new SdkLiveInspectionError(
              "CAPABILITY_UNAVAILABLE",
              "SDK multicam switching can replace only an isolated multicam program on track 1.",
            );
          }
          const clips = [...populated[0].clips].sort((left, right) => left.recordRange.start - right.recordRange.start);
          if (clips.some((clip) => clip.mediaPoolItemId !== multicam.mediaPoolItemId)) {
            throw new SdkLiveInspectionError(
              "CAPABILITY_UNAVAILABLE",
              "The affected track contains non-target content; CutAgent refused whole-program multicam replacement.",
            );
          }
          let cursor = timelineRead.value.start.value.value;
          for (const clip of clips) {
            if (clip.recordRange.start !== cursor || clip.recordRange.endExclusive <= clip.recordRange.start) {
              throw new SdkLiveInspectionError(
                "CAPABILITY_UNAVAILABLE",
                "The target multicam program must be contiguous from the timeline start before whole-program replacement.",
              );
            }
            cursor = clip.recordRange.endExclusive;
          }
          targetRanges.push(cursor);
        }
        if (new Set(targetRanges).size !== 1) {
          throw new SdkLiveInspectionError(
            "CAPABILITY_UNAVAILABLE",
            "Linked multicam video and audio program ranges must match exactly.",
          );
        }
        endFrame = targetRanges[0];
      }
      return Object.freeze({
        timeline: timelineRead.value,
        timelineName: timeline.name,
        timelineNativeId,
        timelineMutationGuard: timelineRead.mutationGuard,
        endFrame,
        multicam,
        sources: Object.freeze(sources),
      });
    },
    async prepareMulticamMatchFrame(input, options = {}) {
      const multicam = await resolveMulticamPrivateTarget(
        input.projectId,
        input.multicamId,
        input.multicamRevision,
        options,
      );
      const angleIndex = multicam.value.angles.findIndex((angle) => angle.id === input.angleId);
      if (angleIndex < 0) {
        throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The referenced multicam angle is not present in this revision.");
      }
      return Object.freeze({ multicam, angleNumber: angleIndex + 1 });
    },
    async prepareMulticamResidualAction(action, input, options = {}) {
      if (action === "settings") {
        const project = (await inspect({ operation: "project.current" }, options)).value;
        if (project.id !== input.projectId) throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed before multicam settings resolution.");
        const sources = await Promise.all(input.sources.map(async (source) => {
          const asset = await resolveMediaPoolPrivateAsset(input.projectId, source.mediaPoolItemId, input.mediaPoolRevision, options);
          if (!asset.sourcePath) throw new SdkLiveInspectionError("CAPABILITY_UNAVAILABLE", "A multicam settings source has no exact local source path.");
          return Object.freeze({ ...source, sourcePath: asset.sourcePath, name: asset.name });
        }));
        return Object.freeze({ project, sources: Object.freeze(sources) });
      }
      if (action === "audio_activity.calibrate") {
        const project = (await inspect({ operation: "project.current" }, options)).value;
        if (project.id !== input.projectId) throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed before multicam calibration.");
        const prepareSources = async (sources) => Promise.all(sources.map(async (source) => {
          const asset = await resolveMediaPoolPrivateAsset(input.projectId, source.mediaPoolItemId, input.mediaPoolRevision, options);
          if (!asset.sourcePath) throw new SdkLiveInspectionError("CAPABILITY_UNAVAILABLE", "A selected calibration source has no exact local source path.");
          return Object.freeze({ ...asset, ...source });
        }));
        return Object.freeze({ project, videoSources: Object.freeze(await prepareSources(input.videoSources)), audioSources: Object.freeze(await prepareSources(input.audioSources)) });
      }
      if (action === "convert") {
        const current = await inspect({ operation: "timeline.current", projectId: input.projectId }, options);
        const snapshot = await inspect({ operation: "timeline.snapshot", projectId: input.projectId, timelineId: input.timelineId }, options);
        if (current.value.id !== input.timelineId || snapshot.value.revision !== input.timelineRevision) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The conversion timeline changed after authoring.");
        }
        const timelineNativeId = text(current.privateExecutionIdentity?.nativeTimelineId);
        if (!timelineNativeId || snapshot.nativeTimelineId !== timelineNativeId) throw new SdkLiveInspectionError("STALE_REVISION", "The native conversion timeline identity changed.");
        return Object.freeze({ timeline: snapshot.value, timelineName: current.value.name, timelineNativeId, timelineMutationGuard: snapshot.mutationGuard });
      }
      const timelineInput = input;
      const preparedTimeline = input.timelineId
        ? await this.prepareMulticamTimelineMutation(timelineInput, options)
        : null;
      const multicam = preparedTimeline?.multicam
        ?? await resolveMulticamPrivateTarget(input.projectId, input.multicamId, input.multicamRevision, options);
      const angleIndex = input.angleId === undefined ? null : multicam.value.angles.findIndex((angle) => angle.id === input.angleId);
      if (input.angleId !== undefined && angleIndex < 0) throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The referenced multicam angle is not present in this revision.");
      let itemIndex = null;
      let sourceNativeId = null;
      if (input.sourceMediaPoolItemId !== undefined) {
        const mediaTypes = action === "source.property_set" ? [input.mediaType]
          : new Set(["source.grade_cdl", "source.raw_braw_set"]).has(action) ? ["video"]
            : input.scope === "both" ? ["video", "audio"] : [input.scope];
        const matches = mediaTypes.map((mediaType) => {
          const rows = multicam.privateSourceBindings?.[angleIndex]?.[mediaType] ?? [];
          const exact = rows.filter((row) => row.mediaPoolItemId === input.sourceMediaPoolItemId);
          if (exact.length !== 1) throw new SdkLiveInspectionError(exact.length ? "AMBIGUOUS_TARGET" : "TARGET_NOT_FOUND", "The referenced multicam source is not one exact source item in the requested media scope.");
          return exact[0];
        });
        if (matches.some((match) => match.itemIndex !== matches[0].itemIndex || match.nativeId !== matches[0].nativeId)) {
          throw new SdkLiveInspectionError("CAPABILITY_UNAVAILABLE", "Linked video/audio source mutation requires one exact paired source identity and item index.");
        }
        itemIndex = matches[0].itemIndex;
        sourceNativeId = matches[0].nativeId;
        if (input.recordFrame !== undefined && matches.some((match) => input.recordFrame < match.startFrame || input.recordFrame >= match.startFrame + match.durationFrames)) {
          throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The requested record frame does not lie inside the exact named multicam source item.");
        }
      }
      const replacementSources = [];
      for (const replacement of input.replacements ?? []) {
        const replacementAngleIndex = multicam.value.angles.findIndex((angle) => angle.id === replacement.angleId);
        if (replacementAngleIndex < 0) throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "A replacement references an angle outside this multicam revision.");
        const asset = await resolveMediaPoolPrivateAsset(input.projectId, replacement.mediaPoolItemId, null, options);
        if (!asset.sourcePath) throw new SdkLiveInspectionError("CAPABILITY_UNAVAILABLE", "A replacement source has no exact local source path.");
        replacementSources.push(Object.freeze({ ...replacement, angleNumber: replacementAngleIndex + 1, sourcePath: asset.sourcePath, name: asset.name }));
      }
      const timingSources = [];
      for (const source of input.sources ?? []) {
        const asset = await resolveMediaPoolPrivateAsset(input.projectId, source.mediaPoolItemId, null, options);
        timingSources.push(Object.freeze({ ...source, nativeId: asset.nativeId, name: asset.name, sourcePath: asset.sourcePath }));
      }
      const smartVideoSources = [];
      const smartAudioSources = [];
      if (action === "smart_switch") {
        const angleIds = new Set(multicam.value.angles.map((angle) => angle.id));
        if (input.audioSources.some((source) => !angleIds.has(source.angleId))
          || input.videoSourceOffsets.some((offset) => !angleIds.has(offset.angleId))
          || (input.wideAngleId !== undefined && !angleIds.has(input.wideAngleId))) {
          throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "SmartSwitch references an angle outside the exact multicam revision.");
        }
        for (const angle of multicam.value.angles) {
          for (const source of angle.sources) {
            const asset = await resolveMediaPoolPrivateAsset(input.projectId, source.mediaPoolItemId, null, options);
            if (!asset.sourcePath) throw new SdkLiveInspectionError("CAPABILITY_UNAVAILABLE", "A SmartSwitch video source has no exact local source path.");
            smartVideoSources.push(Object.freeze({ angleId: angle.id, angleLabel: angle.label, mediaPoolItemId: source.mediaPoolItemId, sourcePath: asset.sourcePath }));
          }
        }
        for (const source of input.audioSources) {
          const asset = await resolveMediaPoolPrivateAsset(input.projectId, source.mediaPoolItemId, null, options);
          if (!asset.sourcePath) throw new SdkLiveInspectionError("CAPABILITY_UNAVAILABLE", "A SmartSwitch audio source has no exact local source path.");
          const angle = multicam.value.angles.find((candidate) => candidate.id === source.angleId);
          smartAudioSources.push(Object.freeze({ ...source, angleLabel: angle.label, sourcePath: asset.sourcePath }));
        }
      }
      return Object.freeze({ ...(preparedTimeline ?? {}), multicam, angleNumber: angleIndex === null ? null : angleIndex + 1, itemIndex, sourceNativeId,
        replacementSources: Object.freeze(replacementSources), timingSources: Object.freeze(timingSources),
        smartVideoSources: Object.freeze(smartVideoSources), smartAudioSources: Object.freeze(smartAudioSources) });
    },
    async readMulticamById(projectId, multicamId, expectedRevision = null, options = {}) {
      return (await resolveMulticamPrivateTarget(projectId, multicamId, expectedRevision, options)).value;
    },
    async readMulticamByName(projectId, multicamName, options = {}) {
      let offset = 0;
      let observedRevision = null;
      const matches = [];
      for (let pages = 0; pages < 31_250; pages += 1) {
        const readRequest = { operation: "mediaPool.page", projectId, offset, pageSize: 32, expectedRevision: observedRevision, search: null };
        const raw = await readSdkLiveInspection("mediaPool.page", { ...options, readRequest });
        const project = currentProject(raw.before, stableIdentityNamespace);
        assertExpected({ project }, projectId);
        const afterProject = readAfterBracket(
          () => currentProject(raw.after, stableIdentityNamespace),
          "The active project changed during multicam creation readback.",
        );
        if (project.id !== afterProject.id || project.name !== afterProject.name) {
          throw new SdkLiveInspectionError("STALE_REVISION", "The active project changed during multicam creation readback.");
        }
        const { value: page } = normalizeMediaPoolPage(raw.summary, project, readRequest);
        observedRevision ??= page.revision;
        for (const entry of raw.summary.entries) {
          if (entry.entry_kind === "asset" && entry.kind === "multicam" && mediaPoolName(entry.name) === multicamName && text(entry.native_id)) {
            matches.push({ name: mediaPoolName(entry.name), nativeId: text(entry.native_id) });
          }
        }
        if (page.nextOffset === null) break;
        offset = page.nextOffset;
      }
      if (matches.length === 0) throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The created multicam clip was not found during readback.");
      if (matches.length > 1) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "The created multicam name is ambiguous during readback.");
      const match = matches[0];
      const mediaPoolItemId = digest("media_pool_item_", { projectId, nativeId: match.nativeId });
      return (await inspect({ operation: "multicam.inspect", projectId, mediaPoolItemId, multicamName, expectedRevision: null }, options)).value;
    },
    async attestManagedProtectedState(request, options = {}) {
      if (request?.operation !== "managed.protected" || !Array.isArray(request.affectedItemIds)) {
        throw new TypeError("Managed protected-state attestation requires exact affected timeline-item identities.");
      }
      const inspected = await inspect({ operation: "timeline.snapshot", projectId: request.projectId, timelineId: request.timelineId }, options);
      if (inspected.value.revision !== request.timelineRevision) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The managed protected-state attestation revision is stale.");
      }
      const affectedIds = [...new Set(request.affectedItemIds)];
      if (affectedIds.length !== request.affectedItemIds.length) return malformed("Managed affected identity closure contains duplicates.");
      const retainedNativeItemIds = request.affectedNativeItemIds ?? [];
      if (!Array.isArray(retainedNativeItemIds) || retainedNativeItemIds.some((id) => typeof id !== "string" || !id)
        || new Set(retainedNativeItemIds).size !== retainedNativeItemIds.length) return malformed("Managed retained native identity closure is invalid.");
      const resolvedNativeItemIds = affectedIds.map((id) => inspected.privateTimelineItemNativeIdByPublicId.get(id));
      if (resolvedNativeItemIds.some((id) => !id)) return malformed("Managed affected identity closure is not authoritatively resolvable.");
      const affectedNativeItemIds = [...new Set(resolvedNativeItemIds)].sort();
      const retainedDatabaseNativeItemIds = [...new Set([...retainedNativeItemIds, ...resolvedNativeItemIds])].sort();
      const raw = await readSdkLiveInspection("managed.protected", { ...options, readRequest: {
        operation: "managed.protected", projectId: request.projectId, timelineId: request.timelineId,
        affectedNativeItemIds, retainedDatabaseNativeItemIds,
      } });
      const before = liveIdentity(raw?.before, stableIdentityNamespace);
      const after = readAfterBracket(() => liveIdentity(raw?.after, stableIdentityNamespace), "The active project or timeline changed during managed protected-state attestation.");
      assertExpected(before, request.projectId, request.timelineId); assertExpected(after, request.projectId, request.timelineId);
      const attestedSnapshot = normalizeSnapshot(raw?.summary, before, after, revisionEvidenceKey);
      const attestation = raw?.attestation;
      const coverage = attestation?.coverage;
      const coverageEvidence = attestation?.coverage_evidence;
      const requiredFamilies = ["fusion", "color", "fairlight", "transitions", "effects", "captions"];
      if (attestedSnapshot.revision !== request.timelineRevision || !/^sha256:[a-f0-9]{64}$/.test(attestation?.protected_state_digest ?? "")
        || !/^sha256:[a-f0-9]{64}$/.test(attestation?.affected_state_digest ?? "")
        || !coverage || requiredFamilies.some((family) => coverage[family] !== true)
        || !plainObject(coverageEvidence) || requiredFamilies.some((family) => text(coverageEvidence[family]).length < 16)
        || JSON.stringify([...(attestation.affected_native_ids ?? [])].sort()) !== JSON.stringify([...affectedNativeItemIds].sort())) {
        return malformed("CutAgent CLI returned incomplete managed protected-family evidence.");
      }
      const affectedVideoClips = inspected.value.tracks
        .filter((track) => track.type === "video")
        .flatMap((track) => track.clips.map((clip) => ({...clip, trackType: track.type, trackIndex: track.index})))
        .filter((clip) => affectedIds.includes(clip.id));
      const retimeStates = [];
      for (const target of affectedVideoClips) {
        const inspectedRetime = await inspect({operation: "timeline.retime", projectId: request.projectId,
          timelineId: request.timelineId, timelineRevision: request.timelineRevision, target}, options);
        retimeStates.push(...inspectedRetime.privateRetimeStates);
      }
      const retimeEmpty = retimeStates.every(isDefaultManagedRetime);
      const affectedStateDigest = `sha256:${crypto.createHash("sha256").update(JSON.stringify(canonicalize({
        protectedFamilies: attestation.affected_state_digest,
        retime: [...retimeStates].sort((left, right) => left.timelineItemId.localeCompare(right.timelineItemId)),
      })), "utf8").digest("hex")}`;
      return Object.freeze({ timelineRevision: attestedSnapshot.revision, protectedStateDigest: attestation.protected_state_digest,
        affectedStateDigest,
        affectedItemIds: Object.freeze(affectedIds),
        privateAffectedNativeItemIds: Object.freeze(retainedDatabaseNativeItemIds),
        affectedProtectedStateEmpty: attestation.affected_protected_state_empty === true && retimeEmpty,
        coverage: Object.freeze(Object.fromEntries([...requiredFamilies, "retime"].map((family) => [family, true]))) });
    },
    async resolveFusionMutationTarget(request, options = {}) {
      if (request?.operation !== "fusion.compositions") {
        throw new TypeError("Fusion mutation target resolution requires the exact composition read contract.");
      }
      const raw = await readSdkLiveInspection(request.operation, { ...options, readRequest: request });
      const before = liveIdentity(raw?.before, stableIdentityNamespace);
      const after = readAfterBracket(
        () => liveIdentity(raw?.after, stableIdentityNamespace),
        "The active project or timeline changed while resolving the Fusion mutation target.",
      );
      assertExpected(before, request.projectId, request.timelineId);
      assertExpected(after, request.projectId, request.timelineId);
      const snapshot = normalizeSnapshot(raw?.summary?.timeline, before, after, revisionEvidenceKey);
      const references = normalizeFusionCompositions(raw?.summary, before, after, request, revisionEvidenceKey, snapshot);
      const reference = references.find((row) => row.id === request.fusionCompositionId);
      if (!reference) throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The exact Fusion composition no longer exists.");
      const item = raw.summary.fusion.items.find((row) => {
        const nativeItemId = text(row?.native_item_id);
        return nativeItemId && digest("timeline_item_", { timelineId: before.timeline.id, nativeId: nativeItemId }) === request.timelineItemId;
      });
      const timelineRows = raw.summary.timeline.tracks.flatMap((track) => Array.isArray(track?.items) ? track.items : []);
      const timelineItem = timelineRows.find((row) => text(row?.timeline_item_unique_id) === text(item?.native_item_id));
      const recordStart = strictInteger(timelineItem?.start);
      const recordEndExclusive = strictInteger(timelineItem?.end);
      const nativeComposition = item?.compositions?.find((row) => strictInteger(row?.index) === reference.index);
      if (!nativeComposition?.graph || typeof nativeComposition.graph !== "object") {
        return malformed("CutAgent CLI did not return exact Fusion graph precondition evidence.");
      }
      if (recordStart === null || recordEndExclusive === null || recordEndExclusive <= recordStart) {
        return malformed("CutAgent CLI did not return exact Fusion target frame bounds.");
      }
      const declaredTargets = Array.isArray(options.protectedTargets) ? options.protectedTargets : [];
      const currentProtectedTargets = fusionProtectedTargets({
        snapshot,
        references,
        projectLibraryId: typeof options.projectLibraryId === "string" ? options.projectLibraryId : null,
        declaredTargets,
      });
      return Object.freeze({
        reference,
        currentProtectedTargets: Object.freeze(currentProtectedTargets.map((target) => Object.freeze(target))),
        nativeTarget: Object.freeze({
          projectNativeId: before.project.id ? text(raw.before.project.project_id) : "",
          timelineNativeId: before.timelineNativeId,
          timelineItemNativeId: text(item?.native_item_id),
          compositionIndex: reference.index,
          compositionName: reference.name,
          nativeGraphEvidence: structuredClone(nativeComposition.graph),
          recordStart,
          recordEndExclusive,
        }),
      });
    },
    async refreshFusionMutationTarget(request, options = {}) {
      if (request?.operation !== "fusion.compositions") {
        throw new TypeError("Fusion mutation target refresh requires the exact composition read contract.");
      }
      const refreshed = await this.resolveFusionMutationTarget(
        { ...request, expectedRevision: null },
        options,
      );
      if (refreshed.reference.id !== request.fusionCompositionId
        || refreshed.reference.projectId !== request.projectId
        || refreshed.reference.timelineId !== request.timelineId
        || refreshed.reference.timelineItemId !== request.timelineItemId) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The exact Fusion composition identity changed after mutation.");
      }
      return refreshed;
    },
    async resolveRenderJobBinding({ projectId, nativeJobId }, options = {}) {
      if (typeof projectId !== "string" || !projectId || typeof nativeJobId !== "string" || !nativeJobId) {
        throw new TypeError("Render job binding requires exact public project and private native job identities.");
      }
      const raw = await readSdkLiveInspection("render.queue", {
        ...options,
        readRequest: { operation: "render.queue", projectId, pageSize: 100, cursor: null },
      });
      if (!raw || typeof raw !== "object" || raw.context_unchanged !== true) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The DaVinci Resolve project or render queue changed while binding the completed render job.");
      }
      const beforeProject = renderProject(raw.before, stableIdentityNamespace);
      const afterProject = renderProject(raw.after, stableIdentityNamespace);
      if (beforeProject.id !== afterProject.id || beforeProject.name !== afterProject.name || beforeProject.id !== projectId) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The referenced DaVinci Resolve project changed while binding the completed render job.");
      }
      const queue = queueState(raw.jobs, beforeProject.id, renderIdentityEvidenceKey);
      const indexes = raw.jobs.jobs
        .map((row, index) => (nullableRenderText(row?.native_id, 1024) === nativeJobId ? index : -1))
        .filter((index) => index >= 0);
      if (indexes.length === 0) throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The completed native render job is no longer present.");
      if (indexes.length > 1) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "The completed native render job identity is ambiguous.");
      const job = queue.jobs[indexes[0]];
      if (!job) return malformed("CutAgent CLI returned an invalid completed render job coordinate.");
      return Object.freeze({ ...job });
    },
    async verifyRenderJobConfiguration({ projectId, nativeJobId, expected }, options = {}) {
      if (typeof projectId !== "string" || !projectId || typeof nativeJobId !== "string" || !nativeJobId
        || !plainObject(expected) || !nullableRenderText(expected.targetDir, 8192)
        || !nullableRenderText(expected.outputFilename, 4096)
        || !Number.isSafeInteger(expected.markInFrame) || !Number.isSafeInteger(expected.markOutFrame)
        || expected.markOutFrame < expected.markInFrame) {
        throw new TypeError("Render job configuration verification requires exact bounded native coordinates.");
      }
      const raw = await readSdkLiveInspection("render.queue", {
        ...options,
        readRequest: { operation: "render.queue", projectId, pageSize: 100, cursor: null },
      });
      if (!raw || typeof raw !== "object" || raw.context_unchanged !== true) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The DaVinci Resolve project or render queue changed while verifying the queued render job.");
      }
      const beforeProject = renderProject(raw.before, stableIdentityNamespace);
      const afterProject = renderProject(raw.after, stableIdentityNamespace);
      if (beforeProject.id !== afterProject.id || beforeProject.name !== afterProject.name || beforeProject.id !== projectId) {
        throw new SdkLiveInspectionError("STALE_REVISION", "The referenced DaVinci Resolve project changed while verifying the queued render job.");
      }
      const matches = raw.jobs.jobs.filter((row) => nullableRenderText(row?.native_id, 1024) === nativeJobId);
      if (matches.length === 0) throw new SdkLiveInspectionError("TARGET_NOT_FOUND", "The queued native render job is no longer present.");
      if (matches.length > 1) throw new SdkLiveInspectionError("AMBIGUOUS_TARGET", "The queued native render job identity is ambiguous.");
      return renderJobConfigurationMatches(matches[0].job, expected);
    },
    async readWorkflowBinding(request, options = {}) {
      if (request.operation !== "timeline.snapshot") throw new TypeError("Workflow binding requires a timeline snapshot.");
      const inspected = await inspect(request, options);
      return Object.freeze({
        projectId: inspected.value.project.id,
        projectName: inspected.value.project.name,
        timelineId: inspected.value.timeline.id,
        timelineName: inspected.value.timeline.name,
        revision: inspected.value.revision,
        nativeTimelineId: inspected.nativeTimelineId,
      });
    },
  };
}
