import {
  DurationSchema,
  FrameRateSchema,
  FramesSchema,
  SecondsSchema,
  SourceRangeSchema,
  SourceTimeSchema,
  TimecodeSchema,
  TimelineRecordRangeSchema,
  TimelineRecordTimeSchema,
  type WireDuration,
  type WireFrameRate,
  type WireFrames,
  type WireSeconds,
  type WireSourceRange,
  type WireSourceTime,
  type WireTimecode,
  type WireTimelineRecordRange,
  type WireTimelineRecordTime,
} from "../schemas/time.js";
import {
  authoringTimeInternals,
  duration,
  frameRate,
  frames,
  seconds,
  sourcePosition,
  sourceRange,
  timecode,
  timelineRecordPosition,
  timelineRecordRange,
  type BoundFrames,
  type Duration,
  type FrameRate,
  type Frames,
  type HydratedDuration,
  type Seconds,
  type SourcePosition,
  type SourceRange,
  type TimeRounding,
  type Timecode,
  type TimelineRecordPosition,
  type TimelineRecordRange,
} from "../value-types/time.js";
import { CutAgentValueError } from "../value-types/value-error.js";

/** Authoritative context supplied by an enclosing snapshot or explicit caller. @beta */
export interface TimeWireContext {
  /** Exact rate inherited from a snapshot or supplied explicitly. */
  readonly frameRate?: FrameRate;
  /** Required only when lowering a non-integral seconds-to-frames conversion. */
  readonly rounding?: TimeRounding;
}

function invalidWire(message: string): never {
  throw new CutAgentValueError("INVALID_TIME_VALUE", message);
}

function parseWire<T>(parse: () => T, label: string): T {
  try {
    return parse();
  } catch {
    return invalidWire(`Invalid ${label} wire value.`);
  }
}

function normalizeContext(value: unknown): TimeWireContext {
  try {
    if (typeof value !== "object" || value === null || Array.isArray(value)) return invalidWire("Time wire context must be an object.");
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) return invalidWire("Time wire context must be a plain object.");
    const keys = Object.keys(value);
    if (keys.some((key) => key !== "frameRate" && key !== "rounding")) return invalidWire("Time wire context contains an unknown field.");
    const candidate = value as { frameRate?: unknown; rounding?: unknown };
    if (candidate.frameRate !== undefined && !authoringTimeInternals.isFrameRate(candidate.frameRate)) {
      return invalidWire("Time wire context frame rate must come from frameRate().");
    }
    if (candidate.rounding !== undefined
      && candidate.rounding !== "floor"
      && candidate.rounding !== "ceil"
      && candidate.rounding !== "nearest_ties_to_even") {
      return invalidWire("Time wire context contains an unknown rounding mode.");
    }
    return {
      ...(candidate.frameRate === undefined ? {} : { frameRate: candidate.frameRate }),
      ...(candidate.rounding === undefined ? {} : { rounding: candidate.rounding }),
    } as TimeWireContext;
  } catch (error) {
    if (error instanceof CutAgentValueError) throw error;
    return invalidWire("Time wire context could not be inspected.");
  }
}

function requiredRate(context: TimeWireContext): FrameRate {
  if (!context.frameRate) throw new CutAgentValueError("FRAME_RATE_REQUIRED", "An exact frame rate is required for this wire conversion.");
  return context.frameRate;
}

function withRate(context: TimeWireContext, rate: FrameRate | null | undefined): TimeWireContext {
  if (context.frameRate && rate && !rate.equals(context.frameRate)) {
    throw new CutAgentValueError("FRAME_RATE_MISMATCH", "Position rate does not match the enclosing wire context.");
  }
  const effectiveRate = context.frameRate ?? rate;
  return effectiveRate ? { ...context, frameRate: effectiveRate } : context;
}

/** Hydrate one exact frame-rate DTO into an ergonomic immutable value. @beta */
export function hydrateFrameRate(value: unknown): FrameRate {
  const wire = parseWire(() => FrameRateSchema.parse(value), "frame-rate");
  return frameRate(wire.numerator, wire.denominator, wire.nominalTimebase);
}

/** Lower one ergonomic frame rate to its versioned shared-contract DTO. @beta */
export function lowerFrameRate(value: FrameRate): WireFrameRate {
  if (!authoringTimeInternals.isFrameRate(value)) return invalidWire("Frame rate must come from frameRate().");
  return FrameRateSchema.parse(value.toJSON());
}

/** Hydrate a wire frame quantity, optionally inheriting an authoritative rate. @beta */
export function hydrateFrames(value: unknown, context: TimeWireContext = {}): Frames | BoundFrames {
  context = normalizeContext(context);
  const wire = parseWire(() => FramesSchema.parse(value), "frames");
  return context.frameRate ? frames(wire.value, context.frameRate) : frames(wire.value);
}

/** Lower an ergonomic frame quantity without inventing a rate. @beta */
export function lowerFrames(value: Frames | BoundFrames): WireFrames {
  if (!authoringTimeInternals.isFrames(value)) return invalidWire("Frames must come from frames().");
  return FramesSchema.parse({ kind: "frames", value: value.value });
}

/** Hydrate legacy numeric wire seconds into canonical microseconds. @beta */
export function hydrateSeconds(value: unknown): Seconds {
  const wire = parseWire(() => SecondsSchema.parse(value), "seconds");
  return seconds(wire.value);
}

/** Lower canonical microseconds to the current finite-number wire DTO. @beta */
export function lowerSeconds(value: Seconds): WireSeconds {
  if (!authoringTimeInternals.isSeconds(value)) return invalidWire("Seconds must come from seconds().");
  const wire = SecondsSchema.parse({ kind: "seconds", value: value.microseconds / 1_000_000 });
  if (seconds(wire.value).microseconds !== value.microseconds) {
    throw new CutAgentValueError("TIME_VALUE_OUT_OF_RANGE", "Seconds cannot round-trip through the current wire contract.");
  }
  return wire;
}

/** Hydrate a validated timecode DTO and its exact rate. @beta */
export function hydrateTimecode(value: unknown): Timecode {
  const wire = parseWire(() => TimecodeSchema.parse(value), "timecode");
  return timecode(wire.value, hydrateFrameRate(wire.rate), wire.dropFrame);
}

/** Lower a validated timecode to its versioned shared-contract DTO. @beta */
export function lowerTimecode(value: Timecode): WireTimecode {
  if (!authoringTimeInternals.isTimecode(value)) return invalidWire("Timecode must come from timecode().");
  return TimecodeSchema.parse({ kind: "timecode", value: value.value, rate: lowerFrameRate(value.rate), dropFrame: value.dropFrame });
}

function lowerPositionValue(value: Frames | BoundFrames | Seconds | Timecode, context: TimeWireContext): WireFrames | WireTimecode {
  if (authoringTimeInternals.isFrames(value)) return lowerFrames(value);
  if (authoringTimeInternals.isTimecode(value)) {
    if (context.frameRate && !value.rate.equals(context.frameRate)) {
      throw new CutAgentValueError("FRAME_RATE_MISMATCH", "Timecode rate does not match the enclosing wire context.");
    }
    return lowerTimecode(value);
  }
  if (authoringTimeInternals.isSeconds(value)) return lowerFrames(value.toFrames(requiredRate(context), context.rounding));
  return invalidWire("Position contains an unknown authoring value.");
}

/** Hydrate a record-domain position with optional enclosing rate context. @beta */
export function hydrateTimelineRecordPosition(value: unknown, context: TimeWireContext = {}): TimelineRecordPosition {
  context = normalizeContext(context);
  const wire = parseWire(() => TimelineRecordTimeSchema.parse(value), "timeline-record position");
  return timelineRecordPosition(
    wire.value.kind === "frames" ? hydrateFrames(wire.value, context) : hydrateTimecode(wire.value),
    context.frameRate,
  );
}

/** Lower a record-domain position. Seconds require a rate and explicit rounding if non-integral. @beta */
export function lowerTimelineRecordPosition(value: TimelineRecordPosition, context: TimeWireContext = {}): WireTimelineRecordTime {
  context = normalizeContext(context);
  if (!authoringTimeInternals.isTimelineRecordPosition(value)) return invalidWire("Record position must come from timelineRecordPosition().");
  return TimelineRecordTimeSchema.parse({ domain: "timeline_record", value: lowerPositionValue(value.value, withRate(context, value.rate)) });
}

/** Hydrate a source-domain position with optional enclosing rate context. @beta */
export function hydrateSourcePosition(value: unknown, context: TimeWireContext = {}): SourcePosition {
  context = normalizeContext(context);
  const wire = parseWire(() => SourceTimeSchema.parse(value), "source position");
  return sourcePosition(
    wire.value.kind === "frames" ? hydrateFrames(wire.value, context) : hydrateTimecode(wire.value),
    context.frameRate,
  );
}

/** Lower a source-domain position without permitting record/source interchange. @beta */
export function lowerSourcePosition(value: SourcePosition, context: TimeWireContext = {}): WireSourceTime {
  context = normalizeContext(context);
  if (!authoringTimeInternals.isSourcePosition(value)) return invalidWire("Source position must come from sourcePosition().");
  return SourceTimeSchema.parse({ domain: "source", value: lowerPositionValue(value.value, withRate(context, value.rate)) });
}

/** Hydrate a non-negative duration; frame durations inherit the enclosing rate when provided. @beta */
export function hydrateDuration(value: unknown, context: TimeWireContext = {}): Duration | HydratedDuration {
  context = normalizeContext(context);
  const wire = parseWire(() => DurationSchema.parse(value), "duration");
  return wire.value.kind === "seconds"
    ? duration(hydrateSeconds(wire.value as WireSeconds))
    : context.frameRate
      ? duration(frames(wire.value.value), context.frameRate)
      : duration(frames(wire.value.value));
}

/** Lower a non-negative authoring duration. Bound rates remain contextual rather than duplicated on wire. @beta */
export function lowerDuration(value: Duration, context: TimeWireContext = {}): WireDuration {
  context = normalizeContext(context);
  if (!authoringTimeInternals.isDuration(value)) return invalidWire("Duration must come from duration().");
  if (value.rate && context.frameRate && !value.rate.equals(context.frameRate)) {
    throw new CutAgentValueError("FRAME_RATE_MISMATCH", "Duration rate does not match the enclosing wire context.");
  }
  return DurationSchema.parse({
    domain: "duration",
    value: value.unit === "seconds" ? lowerSeconds(value.value) : lowerFrames(value.value),
  });
}

function rangeContext(valueRate: FrameRate | null, context: TimeWireContext): TimeWireContext {
  if (valueRate && context.frameRate && !valueRate.equals(context.frameRate)) {
    throw new CutAgentValueError("FRAME_RATE_MISMATCH", "Range rate does not match the enclosing wire context.");
  }
  return withRate(context, valueRate);
}

/** Hydrate a half-open record range, inheriting snapshot rate for frame values. @beta */
export function hydrateTimelineRecordRange(value: unknown, context: TimeWireContext = {}): TimelineRecordRange {
  context = normalizeContext(context);
  const wire = parseWire(() => TimelineRecordRangeSchema.parse(value), "timeline-record range");
  if (wire.unit === "seconds") return timelineRecordRange(seconds(wire.start), seconds(wire.endExclusive), context.frameRate);
  const start = context.frameRate ? frames(wire.start, context.frameRate) : frames(wire.start);
  const end = context.frameRate ? frames(wire.endExclusive, context.frameRate) : frames(wire.endExclusive);
  return timelineRecordRange(start, end, context.frameRate);
}

/** Lower a half-open record range to one homogeneous wire unit. @beta */
export function lowerTimelineRecordRange(value: TimelineRecordRange, context: TimeWireContext = {}): WireTimelineRecordRange {
  context = normalizeContext(context);
  if (!authoringTimeInternals.isTimelineRecordRange(value)) return invalidWire("Record range must come from timelineRecordRange().");
  const effective = rangeContext(value.rate, context);
  const start = value.start.value;
  const end = value.endExclusive.value;
  if (authoringTimeInternals.isSeconds(start) && authoringTimeInternals.isSeconds(end)) {
    return TimelineRecordRangeSchema.parse({ domain: "timeline_record_range", unit: "seconds", start: lowerSeconds(start).value, endExclusive: lowerSeconds(end).value });
  }
  const startFrames = lowerPositionValue(start, effective);
  const endFrames = lowerPositionValue(end, effective);
  const toFrameNumber = (position: WireFrames | WireTimecode) => position.kind === "frames" ? position.value : hydrateTimecode(position).toFrames().value;
  return TimelineRecordRangeSchema.parse({ domain: "timeline_record_range", unit: "frames", start: toFrameNumber(startFrames), endExclusive: toFrameNumber(endFrames) });
}

/** Hydrate a half-open source range, inheriting snapshot rate for frame values. @beta */
export function hydrateSourceRange(value: unknown, context: TimeWireContext = {}): SourceRange {
  context = normalizeContext(context);
  const wire = parseWire(() => SourceRangeSchema.parse(value), "source range");
  if (wire.unit === "seconds") return sourceRange(seconds(wire.start), seconds(wire.endExclusive), context.frameRate);
  const start = context.frameRate ? frames(wire.start, context.frameRate) : frames(wire.start);
  const end = context.frameRate ? frames(wire.endExclusive, context.frameRate) : frames(wire.endExclusive);
  return sourceRange(start, end, context.frameRate);
}

/** Lower a half-open source range without permitting record/source interchange. @beta */
export function lowerSourceRange(value: SourceRange, context: TimeWireContext = {}): WireSourceRange {
  context = normalizeContext(context);
  if (!authoringTimeInternals.isSourceRange(value)) return invalidWire("Source range must come from sourceRange().");
  const effective = rangeContext(value.rate, context);
  const start = value.start.value;
  const end = value.endExclusive.value;
  if (authoringTimeInternals.isSeconds(start) && authoringTimeInternals.isSeconds(end)) {
    return SourceRangeSchema.parse({ domain: "source_range", unit: "seconds", start: lowerSeconds(start).value, endExclusive: lowerSeconds(end).value });
  }
  const startFrames = lowerPositionValue(start, effective);
  const endFrames = lowerPositionValue(end, effective);
  const toFrameNumber = (position: WireFrames | WireTimecode) => position.kind === "frames" ? position.value : hydrateTimecode(position).toFrames().value;
  return SourceRangeSchema.parse({ domain: "source_range", unit: "frames", start: toFrameNumber(startFrames), endExclusive: toFrameNumber(endFrames) });
}
