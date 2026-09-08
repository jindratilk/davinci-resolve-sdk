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
  TimestampSchema,
  type WireDuration,
  type WireFrameRate,
  type WireFrames,
  type WireSeconds,
  type WireSourceRange,
  type WireSourceTime,
  type WireTimecode,
  type WireTimelineRecordRange,
  type WireTimelineRecordTime,
  type Timestamp,
} from "../schemas/time.js";
import { CutAgentValueError } from "../value-types/value-error.js";

function invalidPreview(message: string): never {
  throw new CutAgentValueError("INVALID_TIME_VALUE", message);
}

function parsePreview<T>(parse: () => T, label: string): T {
  try {
    return parse();
  } catch (error) {
    if (error instanceof CutAgentValueError) throw error;
    return invalidPreview(`Invalid legacy ${label}.`);
  }
}

/** @beta */ export type Frames = WireFrames;
/** @beta */ export type Seconds = WireSeconds;
/** @beta */ export type FrameRate = WireFrameRate;
/** @beta */ export type Timecode = WireTimecode;
/** @beta */ export type TimelineRecordTime = WireTimelineRecordTime;
/** @beta */ export type SourceTime = WireSourceTime;
/** @beta */ export type Duration = WireDuration;
/** @beta */ export type TimelineRecordRange = WireTimelineRecordRange;
/** @beta */ export type SourceRange = WireSourceRange;
/** @beta */ export type { Timestamp };

export {
  DurationSchema,
  FrameRateSchema,
  FramesSchema,
  SecondsSchema,
  SourceRangeSchema,
  SourceTimeSchema,
  TimecodeSchema,
  TimelineRecordRangeSchema,
  TimelineRecordTimeSchema,
  TimestampSchema,
};

/** Legacy 0.1 DTO factory. Prefer root `frames()`. @beta */
export function frames(value: number): Frames {
  return parsePreview(() => FramesSchema.parse({ kind: "frames", value }), "frames");
}
/** Legacy 0.1 DTO factory. Prefer root `seconds()`. @beta */
export function seconds(value: number): Seconds {
  return parsePreview(() => SecondsSchema.parse({ kind: "seconds", value }), "seconds");
}
/** Legacy 0.1 DTO factory. Prefer root `frameRate()`. @beta */
export function frameRate(numerator: number, denominator: number, nominalTimebase: number): FrameRate {
  return parsePreview(() => FrameRateSchema.parse({ numerator, denominator, nominalTimebase }), "frame rate");
}
/** Legacy 0.1 DTO factory. Prefer root `timecode()`. @beta */
export function timecode(value: string, rate: FrameRate, dropFrame?: boolean): Timecode {
  if (typeof value !== "string") return invalidPreview("Legacy timecode label must be a string.");
  if (dropFrame !== undefined && typeof dropFrame !== "boolean") return invalidPreview("Legacy drop-frame mode must be boolean.");
  return parsePreview(
    () => TimecodeSchema.parse({ kind: "timecode", value, rate, dropFrame: dropFrame ?? value.includes(";") }),
    "timecode",
  );
}

/** Legacy 0.1 timecode conversion. @beta */
export function timecodeToFrames(value: Timecode, expectedRate?: FrameRate): Frames {
  const validated = parsePreview(() => TimecodeSchema.parse(value), "timecode");
  const rate = parsePreview(() => FrameRateSchema.parse(expectedRate === undefined ? validated.rate : expectedRate), "frame rate");
  if (JSON.stringify(validated.rate) !== JSON.stringify(rate)) {
    throw new CutAgentValueError("FRAME_RATE_MISMATCH", "Legacy timecode frame rate must match the expected frame rate.");
  }
  const match = /^(\d{2,}):([0-5]\d):([0-5]\d)([:;])(\d+)$/.exec(validated.value);
  if (!match) return invalidPreview("Legacy timecode label is invalid.");
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  const secondsValue = Number(match[3]);
  const frame = Number(match[5]);
  const totalMinutes = hours * 60 + minutes;
  let result = ((hours * 3600 + minutes * 60 + secondsValue) * rate.nominalTimebase) + frame;
  if (validated.dropFrame) {
    const droppedPerMinute = rate.nominalTimebase === 60 ? 4 : 2;
    result -= droppedPerMinute * (totalMinutes - Math.floor(totalMinutes / 10));
  }
  return frames(result);
}

/** Legacy 0.1 record-position normalization. @beta */
export function timelineRecordFrames(position: Frames | Timecode | TimelineRecordTime, expectedRate: FrameRate): Frames {
  const rate = parsePreview(() => FrameRateSchema.parse(expectedRate), "frame rate");
  const record = TimelineRecordTimeSchema.safeParse(position);
  const value = record.success ? record.data.value : position;
  const frame = FramesSchema.safeParse(value);
  return frame.success
    ? frame.data
    : timecodeToFrames(parsePreview(() => TimecodeSchema.parse(value), "record position"), rate);
}
