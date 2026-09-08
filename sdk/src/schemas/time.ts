import { z } from "zod";

/** ISO-8601 instant with an explicit offset. @beta */
export const TimestampSchema = z.iso.datetime({ offset: true }).brand<"Timestamp">();
/** ISO-8601 instant with an explicit offset. @beta */
export type Timestamp = z.infer<typeof TimestampSchema>;

/** Integer frame count on the versioned wire contract. @beta */
export const FramesSchema = z.strictObject({ kind: z.literal("frames"), value: z.number().int() }).brand<"Frames">();
/** Integer frame count on the versioned wire contract. @beta */
export type WireFrames = z.infer<typeof FramesSchema>;

/** Finite seconds value on the versioned wire contract. @beta */
export const SecondsSchema = z.strictObject({ kind: z.literal("seconds"), value: z.number().finite() }).brand<"Seconds">();
/** Finite seconds value on the versioned wire contract. @beta */
export type WireSeconds = z.infer<typeof SecondsSchema>;

function greatestCommonDivisor(left: number, right: number): number {
  let a = left;
  let b = right;
  while (b !== 0) {
    const remainder = a % b;
    a = b;
    b = remainder;
  }
  return a;
}

/** Exact frame-rate identity on the versioned wire contract. @beta */
export const FrameRateSchema = z
  .strictObject({
    numerator: z.number().int().positive().max(1_000_000),
    denominator: z.number().int().positive().max(1_000_000),
    nominalTimebase: z.number().int().positive().max(1000),
  })
  .superRefine((rate, context) => {
    if (greatestCommonDivisor(rate.numerator, rate.denominator) !== 1) {
      context.addIssue({ code: "custom", message: "Frame rate rational must be reduced" });
    }
    const calculatedNominalTimebase = Math.floor((rate.numerator + rate.denominator - 1) / rate.denominator);
    if (calculatedNominalTimebase !== rate.nominalTimebase) {
      context.addIssue({ code: "custom", message: "Nominal timebase must equal the ceiling of the actual rate" });
    }
  })
  .brand<"FrameRate">();
/** Exact frame-rate identity on the versioned wire contract. @beta */
export type WireFrameRate = z.infer<typeof FrameRateSchema>;

const timecodeLabel = /^(\d{2,}):([0-5]\d):([0-5]\d)([:;])(\d+)$/;

function isDropFrameRate(rate: WireFrameRate): boolean {
  return (
    (rate.numerator === 30_000 && rate.denominator === 1001 && rate.nominalTimebase === 30) ||
    (rate.numerator === 60_000 && rate.denominator === 1001 && rate.nominalTimebase === 60)
  );
}

/** SMPTE-like timecode label on the versioned wire contract. @beta */
export const TimecodeSchema = z
  .strictObject({
    kind: z.literal("timecode"),
    value: z.string(),
    rate: FrameRateSchema,
    dropFrame: z.boolean(),
  })
  .superRefine((timecodeValue, context) => {
    const match = timecodeLabel.exec(timecodeValue.value);
    if (!match) {
      context.addIssue({ code: "custom", path: ["value"], message: "Invalid timecode label" });
      return;
    }
    const minute = Number(match[2]);
    const second = Number(match[3]);
    const separator = match[4];
    const frameText = match[5];
    if (frameText === undefined) return;
    const expectedWidth = Math.max(2, String(timecodeValue.rate.nominalTimebase - 1).length);
    if (frameText.length !== expectedWidth) {
      context.addIssue({ code: "custom", path: ["value"], message: `Frame field must contain exactly ${expectedWidth} digits` });
    }
    const frame = Number(frameText);
    if (!Number.isSafeInteger(frame) || frame >= timecodeValue.rate.nominalTimebase) {
      context.addIssue({ code: "custom", path: ["value"], message: "Timecode frame field exceeds its nominal timebase" });
    }
    if (timecodeValue.dropFrame !== (separator === ";")) {
      context.addIssue({ code: "custom", path: ["value"], message: "Timecode separator and dropFrame must agree" });
    }
    if (timecodeValue.dropFrame && !isDropFrameRate(timecodeValue.rate)) {
      context.addIssue({ code: "custom", path: ["rate"], message: "Drop-frame labels require 30000/1001 or 60000/1001" });
      return;
    }
    if (timecodeValue.dropFrame && minute % 10 !== 0 && second === 0) {
      const droppedLabels = timecodeValue.rate.nominalTimebase === 30 ? 2 : 4;
      if (frame < droppedLabels) {
        context.addIssue({ code: "custom", path: ["value"], message: "Timecode label is skipped by drop-frame numbering" });
      }
    }
  })
  .brand<"Timecode">();
/** SMPTE-like timecode label on the versioned wire contract. @beta */
export type WireTimecode = z.infer<typeof TimecodeSchema>;

/** Timeline-record position DTO. @beta */
export const TimelineRecordTimeSchema = z
  .strictObject({ domain: z.literal("timeline_record"), value: z.union([FramesSchema, TimecodeSchema]) })
  .brand<"TimelineRecordTime">();
/** Timeline-record position DTO. @beta */
export type WireTimelineRecordTime = z.infer<typeof TimelineRecordTimeSchema>;

/** Source position DTO. @beta */
export const SourceTimeSchema = z
  .strictObject({ domain: z.literal("source"), value: z.union([FramesSchema, TimecodeSchema]) })
  .brand<"SourceTime">();
/** Source position DTO. @beta */
export type WireSourceTime = z.infer<typeof SourceTimeSchema>;

/** Non-negative duration DTO. @beta */
export const DurationSchema = z
  .union([
    z.strictObject({ domain: z.literal("duration"), value: z.strictObject({ kind: z.literal("frames"), value: z.number().int().nonnegative() }) }),
    z.strictObject({ domain: z.literal("duration"), value: z.strictObject({ kind: z.literal("seconds"), value: z.number().finite().nonnegative() }) }),
  ])
  .brand<"Duration">();
/** Non-negative duration DTO. @beta */
export type WireDuration = z.infer<typeof DurationSchema>;

const timelineFrameRange = z
  .strictObject({ domain: z.literal("timeline_record_range"), unit: z.literal("frames"), start: z.number().int(), endExclusive: z.number().int() })
  .refine((range) => range.endExclusive > range.start, "Range end must be after start");
const timelineSecondsRange = z
  .strictObject({ domain: z.literal("timeline_record_range"), unit: z.literal("seconds"), start: z.number().finite(), endExclusive: z.number().finite() })
  .refine((range) => range.endExclusive > range.start, "Range end must be after start");
/** Half-open timeline-record range DTO. @beta */
export const TimelineRecordRangeSchema = z.union([timelineFrameRange, timelineSecondsRange]).brand<"TimelineRecordRange">();
/** Half-open timeline-record range DTO. @beta */
export type WireTimelineRecordRange = z.infer<typeof TimelineRecordRangeSchema>;

const sourceFrameRange = z
  .strictObject({ domain: z.literal("source_range"), unit: z.literal("frames"), start: z.number().int(), endExclusive: z.number().int() })
  .refine((range) => range.endExclusive > range.start, "Range end must be after start");
const sourceSecondsRange = z
  .strictObject({ domain: z.literal("source_range"), unit: z.literal("seconds"), start: z.number().finite(), endExclusive: z.number().finite() })
  .refine((range) => range.endExclusive > range.start, "Range end must be after start");
/** Half-open source range DTO. @beta */
export const SourceRangeSchema = z.union([sourceFrameRange, sourceSecondsRange]).brand<"SourceRange">();
/** Half-open source range DTO. @beta */
export type WireSourceRange = z.infer<typeof SourceRangeSchema>;
