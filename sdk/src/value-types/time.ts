const MAX_RATE_COMPONENT = 1_000_000;
const MAX_NOMINAL_TIMEBASE = 1000;
const MICROSECONDS_PER_SECOND = 1_000_000n;
const MAX_SAFE_INTEGER_BIGINT = BigInt(Number.MAX_SAFE_INTEGER);
const MIN_SAFE_INTEGER_BIGINT = BigInt(Number.MIN_SAFE_INTEGER);
const TIMECODE_PATTERN = /^(\d{2,}):([0-5]\d):([0-5]\d)([:;])(\d+)$/;

import { CutAgentValueError, type CutAgentValueErrorCode } from "./value-error.js";
export { CutAgentValueError, type CutAgentValueErrorCode } from "./value-error.js";

/** Caller-selected rounding for a non-integral frame conversion. @beta */
export type TimeRounding = "floor" | "ceil" | "nearest_ties_to_even";

declare const frameRateBrand: unique symbol;
declare const framesBrand: unique symbol;
declare const boundFramesBrand: unique symbol;
declare const secondsBrand: unique symbol;
declare const timecodeBrand: unique symbol;
declare const durationBrand: unique symbol;
declare const timelineRecordPositionBrand: unique symbol;
declare const sourcePositionBrand: unique symbol;
declare const timelineRecordRangeBrand: unique symbol;
declare const sourceRangeBrand: unique symbol;

/** Exact reduced rational frame-rate identity with an explicit nominal timebase. @beta */
export interface FrameRate {
  readonly numerator: number;
  readonly denominator: number;
  readonly nominalTimebase: number;
  readonly [frameRateBrand]: true;
  equals(other: FrameRate): boolean;
  toJSON(): Readonly<{ numerator: number; denominator: number; nominalTimebase: number }>;
  toString(): string;
}

/** Rate-unbound integer frame quantity. Bind it before cross-unit work. @beta */
export interface Frames {
  readonly kind: "frames";
  readonly value: number;
  readonly rate: null;
  readonly [framesBrand]: true;
  bind(rate: FrameRate): BoundFrames;
  compare(other: Frames): number;
  eq(other: Frames): boolean;
  lt(other: Frames): boolean;
  lte(other: Frames): boolean;
  gt(other: Frames): boolean;
  gte(other: Frames): boolean;
  add(other: Frames): Frames;
  subtract(other: Frames): Frames;
  /** Convert to canonical microseconds. Non-integral microseconds require an explicit rounding rule. */
  toSeconds(rate: FrameRate, rounding?: TimeRounding): Seconds;
  toJSON(): Readonly<{ kind: "frames"; value: number }>;
  toString(): string;
}

/** Integer frame quantity carrying one exact authoritative rate. @beta */
export interface BoundFrames {
  readonly kind: "frames";
  readonly value: number;
  readonly rate: FrameRate;
  readonly [boundFramesBrand]: true;
  compare(other: Frames | BoundFrames | Seconds): number;
  eq(other: Frames | BoundFrames | Seconds): boolean;
  lt(other: Frames | BoundFrames | Seconds): boolean;
  lte(other: Frames | BoundFrames | Seconds): boolean;
  gt(other: Frames | BoundFrames | Seconds): boolean;
  gte(other: Frames | BoundFrames | Seconds): boolean;
  add(other: Frames | BoundFrames): BoundFrames;
  add(other: Seconds, rounding?: TimeRounding): BoundFrames;
  subtract(other: Frames | BoundFrames): BoundFrames;
  subtract(other: Seconds, rounding?: TimeRounding): BoundFrames;
  /** Convert to canonical microseconds. Non-integral microseconds require an explicit rounding rule. */
  toSeconds(rounding?: TimeRounding): Seconds;
  toJSON(): Readonly<{ kind: "frames"; value: number; rate: ReturnType<FrameRate["toJSON"]> }>;
  toString(): string;
}

/** Exact decimal seconds normalized to an integer microsecond count. @beta */
export interface Seconds {
  readonly kind: "seconds";
  readonly microseconds: number;
  readonly [secondsBrand]: true;
  compare(other: Seconds): number;
  compare(other: BoundFrames): number;
  compare(other: Frames, rate: FrameRate): number;
  eq(other: Seconds): boolean;
  eq(other: BoundFrames): boolean;
  eq(other: Frames, rate: FrameRate): boolean;
  lt(other: Seconds): boolean;
  lt(other: BoundFrames): boolean;
  lt(other: Frames, rate: FrameRate): boolean;
  lte(other: Seconds): boolean;
  lte(other: BoundFrames): boolean;
  lte(other: Frames, rate: FrameRate): boolean;
  gt(other: Seconds): boolean;
  gt(other: BoundFrames): boolean;
  gt(other: Frames, rate: FrameRate): boolean;
  gte(other: Seconds): boolean;
  gte(other: BoundFrames): boolean;
  gte(other: Frames, rate: FrameRate): boolean;
  add(other: Seconds): Seconds;
  subtract(other: Seconds): Seconds;
  toFrames(rate: FrameRate, rounding?: TimeRounding): BoundFrames;
  toJSON(): Readonly<{ kind: "seconds"; microseconds: number }>;
  toString(): string;
}

/** Validated SMPTE-like label carrying its exact frame rate. @beta */
export interface Timecode {
  readonly kind: "timecode";
  readonly value: string;
  readonly rate: FrameRate;
  readonly dropFrame: boolean;
  readonly [timecodeBrand]: true;
  equals(other: Timecode): boolean;
  toFrames(): BoundFrames;
  toJSON(): Readonly<{ kind: "timecode"; value: string; rate: ReturnType<FrameRate["toJSON"]>; dropFrame: boolean }>;
  toString(): string;
}

/** Non-negative duration expressed in canonical decimal seconds. @beta */
export interface SecondsDuration {
  readonly domain: "duration";
  readonly unit: "seconds";
  readonly value: Seconds;
  readonly rate: null;
  readonly [durationBrand]: "seconds";
  compare(other: Seconds | SecondsDuration | BoundFrameDuration): number;
  compare(other: Frames | FrameDuration, rate: FrameRate): number;
  eq(other: Seconds | SecondsDuration | BoundFrameDuration): boolean;
  eq(other: Frames | FrameDuration, rate: FrameRate): boolean;
  lt(other: Seconds | SecondsDuration | BoundFrameDuration): boolean;
  lt(other: Frames | FrameDuration, rate: FrameRate): boolean;
  lte(other: Seconds | SecondsDuration | BoundFrameDuration): boolean;
  lte(other: Frames | FrameDuration, rate: FrameRate): boolean;
  gt(other: Seconds | SecondsDuration | BoundFrameDuration): boolean;
  gt(other: Frames | FrameDuration, rate: FrameRate): boolean;
  gte(other: Seconds | SecondsDuration | BoundFrameDuration): boolean;
  gte(other: Frames | FrameDuration, rate: FrameRate): boolean;
  add(other: Seconds | SecondsDuration): SecondsDuration;
  subtract(other: Seconds | SecondsDuration): SecondsDuration;
  toFrames(rate: FrameRate, rounding?: TimeRounding): BoundFrameDuration;
  toJSON(): Readonly<{ domain: "duration"; value: ReturnType<Seconds["toJSON"]> }>;
  toString(): string;
}

/** Non-negative frame duration without rate context. @beta */
export interface FrameDuration {
  readonly domain: "duration";
  readonly unit: "frames";
  readonly value: Frames;
  readonly rate: null;
  readonly [durationBrand]: "unbound_frames";
  bind(rate: FrameRate): BoundFrameDuration;
  compare(other: Frames | FrameDuration): number;
  compare(other: Seconds | SecondsDuration | BoundFrameDuration, rate: FrameRate): number;
  eq(other: Frames | FrameDuration): boolean;
  eq(other: Seconds | SecondsDuration | BoundFrameDuration, rate: FrameRate): boolean;
  lt(other: Frames | FrameDuration): boolean;
  lt(other: Seconds | SecondsDuration | BoundFrameDuration, rate: FrameRate): boolean;
  lte(other: Frames | FrameDuration): boolean;
  lte(other: Seconds | SecondsDuration | BoundFrameDuration, rate: FrameRate): boolean;
  gt(other: Frames | FrameDuration): boolean;
  gt(other: Seconds | SecondsDuration | BoundFrameDuration, rate: FrameRate): boolean;
  gte(other: Frames | FrameDuration): boolean;
  gte(other: Seconds | SecondsDuration | BoundFrameDuration, rate: FrameRate): boolean;
  add(other: Frames | FrameDuration): FrameDuration;
  subtract(other: Frames | FrameDuration): FrameDuration;
  toJSON(): Readonly<{ domain: "duration"; value: ReturnType<Frames["toJSON"]> }>;
  toString(): string;
}

/** Non-negative frame duration carrying its authoritative rate. @beta */
export interface BoundFrameDuration {
  readonly domain: "duration";
  readonly unit: "frames";
  readonly value: BoundFrames;
  readonly rate: FrameRate;
  readonly [durationBrand]: "bound_frames";
  compare(other: Frames | BoundFrames | FrameDuration | BoundFrameDuration | Seconds | SecondsDuration): number;
  eq(other: Frames | BoundFrames | FrameDuration | BoundFrameDuration | Seconds | SecondsDuration): boolean;
  lt(other: Frames | BoundFrames | FrameDuration | BoundFrameDuration | Seconds | SecondsDuration): boolean;
  lte(other: Frames | BoundFrames | FrameDuration | BoundFrameDuration | Seconds | SecondsDuration): boolean;
  gt(other: Frames | BoundFrames | FrameDuration | BoundFrameDuration | Seconds | SecondsDuration): boolean;
  gte(other: Frames | BoundFrames | FrameDuration | BoundFrameDuration | Seconds | SecondsDuration): boolean;
  add(other: Frames | BoundFrames | FrameDuration | BoundFrameDuration): BoundFrameDuration;
  add(other: Seconds | SecondsDuration, rounding?: TimeRounding): BoundFrameDuration;
  subtract(other: Frames | BoundFrames | FrameDuration | BoundFrameDuration): BoundFrameDuration;
  subtract(other: Seconds | SecondsDuration, rounding?: TimeRounding): BoundFrameDuration;
  /** Convert to canonical microseconds. Non-integral microseconds require an explicit rounding rule. */
  toSeconds(rounding?: TimeRounding): Seconds;
  toJSON(): Readonly<{ domain: "duration"; value: ReturnType<BoundFrames["toJSON"]> }>;
  toString(): string;
}

/** Any standalone duration. Snapshot hydration never returns an unbound frame duration. @beta */
export type Duration = SecondsDuration | FrameDuration | BoundFrameDuration;
/** Duration whose cross-unit comparisons have authoritative context. @beta */
export type HydratedDuration = SecondsDuration | BoundFrameDuration;

/** Position in the timeline-record domain. @beta */
export interface TimelineRecordPosition {
  readonly domain: "timeline_record";
  readonly value: Frames | BoundFrames | Seconds | Timecode;
  readonly rate: FrameRate | null;
  readonly [timelineRecordPositionBrand]: true;
  toJSON(): Readonly<{ domain: "timeline_record"; value: unknown }>;
  toString(): string;
}

/** Timeline-record position narrowed to one accepted authoring value family. @beta */
export interface TimelineRecordPositionOf<Value extends PositionValue> extends TimelineRecordPosition {
  readonly value: Value;
}

/** Position in a media-source domain. @beta */
export interface SourcePosition {
  readonly domain: "source";
  readonly value: Frames | BoundFrames | Seconds | Timecode;
  readonly rate: FrameRate | null;
  readonly [sourcePositionBrand]: true;
  toJSON(): Readonly<{ domain: "source"; value: unknown }>;
  toString(): string;
}

/** Source position narrowed to one accepted authoring value family. @beta */
export interface SourcePositionOf<Value extends PositionValue> extends SourcePosition {
  readonly value: Value;
}

/** Half-open `[start, end)` range in the timeline-record domain. @beta */
export interface TimelineRecordRange {
  readonly domain: "timeline_record_range";
  readonly start: TimelineRecordPosition;
  readonly endExclusive: TimelineRecordPosition;
  readonly rate: FrameRate | null;
  readonly [timelineRecordRangeBrand]: true;
  toJSON(): Readonly<{ domain: "timeline_record_range"; start: unknown; endExclusive: unknown }>;
  toString(): string;
}

/** Timeline-record range narrowed to its homogeneous authoring value families. @beta */
export interface TimelineRecordRangeOf<Value extends PositionValue> extends TimelineRecordRange {
  readonly start: TimelineRecordPositionOf<Value>;
  readonly endExclusive: TimelineRecordPositionOf<Value>;
}

/** Half-open `[start, end)` range in a media-source domain. @beta */
export interface SourceRange {
  readonly domain: "source_range";
  readonly start: SourcePosition;
  readonly endExclusive: SourcePosition;
  readonly rate: FrameRate | null;
  readonly [sourceRangeBrand]: true;
  toJSON(): Readonly<{ domain: "source_range"; start: unknown; endExclusive: unknown }>;
  toString(): string;
}

/** Source range narrowed to its homogeneous authoring value families. @beta */
export interface SourceRangeOf<Value extends PositionValue> extends SourceRange {
  readonly start: SourcePositionOf<Value>;
  readonly endExclusive: SourcePositionOf<Value>;
}

/** Value accepted by record/source position factories. @beta */
export type PositionValue = Frames | BoundFrames | Seconds | Timecode;
type DurationInput = Frames | BoundFrames | Seconds;
type Rational = Readonly<{ numerator: bigint; denominator: bigint }>;

interface TimeIdentityRegistry {
  rates: WeakSet<object>;
  frames: WeakSet<object>;
  boundFrames: WeakSet<object>;
  seconds: WeakSet<object>;
  timecodes: WeakSet<object>;
  durations: WeakSet<object>;
  timelinePositions: WeakSet<object>;
  sourcePositions: WeakSet<object>;
  timelineRanges: WeakSet<object>;
  sourceRanges: WeakSet<object>;
}

const registryKey = Symbol.for("cutagent.authoring-time.v1");
const globalRegistry = globalThis as unknown as Record<symbol, TimeIdentityRegistry | undefined>;
const identityRegistry = globalRegistry[registryKey] ??= {
  rates: new WeakSet(), frames: new WeakSet(), boundFrames: new WeakSet(), seconds: new WeakSet(),
  timecodes: new WeakSet(), durations: new WeakSet(), timelinePositions: new WeakSet(),
  sourcePositions: new WeakSet(), timelineRanges: new WeakSet(), sourceRanges: new WeakSet(),
};
const knownRates = identityRegistry.rates;
const knownFrames = identityRegistry.frames;
const knownBoundFrames = identityRegistry.boundFrames;
const knownSeconds = identityRegistry.seconds;
const knownTimecodes = identityRegistry.timecodes;
const knownDurations = identityRegistry.durations;
const knownTimelinePositions = identityRegistry.timelinePositions;
const knownSourcePositions = identityRegistry.sourcePositions;
const knownTimelineRanges = identityRegistry.timelineRanges;
const knownSourceRanges = identityRegistry.sourceRanges;

function fail(code: CutAgentValueErrorCode, message: string): never {
  throw new CutAgentValueError(code, message);
}

function safeInteger(value: bigint, context: string): number {
  if (value > MAX_SAFE_INTEGER_BIGINT || value < MIN_SAFE_INTEGER_BIGINT) {
    return fail("TIME_VALUE_OUT_OF_RANGE", `${context} exceeds the public safe-integer range.`);
  }
  return Number(value);
}

function gcd(left: number, right: number): number {
  let a = Math.abs(left);
  let b = Math.abs(right);
  while (b !== 0) [a, b] = [b, a % b];
  return a;
}

function validateRate(value: FrameRate): FrameRate {
  if (!knownRates.has(value as object)) return fail("INVALID_TIME_VALUE", "Frame rate must come from frameRate().");
  return value;
}

function ratesEqual(left: FrameRate, right: FrameRate): boolean {
  return left.numerator === right.numerator
    && left.denominator === right.denominator
    && left.nominalTimebase === right.nominalTimebase;
}

function requireMatchingRates(left: FrameRate, right: FrameRate): void {
  if (!ratesEqual(left, right)) fail("FRAME_RATE_MISMATCH", `Frame rates ${left.toString()} and ${right.toString()} do not match.`);
}

/** Construct a reduced exact frame rate. The nominal timebase defaults to the rational ceiling. @beta */
export function frameRate(numerator: number, denominator: number, nominalTimebase?: number): FrameRate {
  if (!Number.isSafeInteger(numerator) || numerator <= 0 || numerator > MAX_RATE_COMPONENT
    || !Number.isSafeInteger(denominator) || denominator <= 0 || denominator > MAX_RATE_COMPONENT
    || gcd(numerator, denominator) !== 1) {
    return fail("INVALID_TIME_VALUE", "Frame-rate components must be positive, bounded, reduced integers.");
  }
  const expectedNominal = Math.ceil(numerator / denominator);
  const nominal = nominalTimebase ?? expectedNominal;
  if (!Number.isSafeInteger(nominal) || nominal <= 0 || nominal > MAX_NOMINAL_TIMEBASE || nominal !== expectedNominal) {
    return fail("INVALID_TIME_VALUE", "Nominal timebase must equal the ceiling of the exact frame rate.");
  }
  const rate = {
    numerator,
    denominator,
    nominalTimebase: nominal,
    equals(other: FrameRate) { return knownRates.has(other as object) && ratesEqual(rate as FrameRate, other); },
    toJSON() { return { numerator, denominator, nominalTimebase: nominal } as const; },
    toString() { return `${numerator}/${denominator} (${nominal} fps timebase)`; },
  } as unknown as FrameRate;
  knownRates.add(rate as object);
  return Object.freeze(rate);
}

function frameRational(value: number, rate: FrameRate): Rational {
  return { numerator: BigInt(value) * BigInt(rate.denominator), denominator: BigInt(rate.numerator) };
}

function secondsRational(value: Seconds): Rational {
  return { numerator: BigInt(value.microseconds), denominator: MICROSECONDS_PER_SECOND };
}

function compareRational(left: Rational, right: Rational): number {
  const difference = left.numerator * right.denominator - right.numerator * left.denominator;
  return difference < 0n ? -1 : difference > 0n ? 1 : 0;
}

function validateRounding(rounding?: TimeRounding): TimeRounding | undefined {
  if (rounding !== undefined
    && rounding !== "floor"
    && rounding !== "ceil"
    && rounding !== "nearest_ties_to_even") {
    return fail("INVALID_TIME_VALUE", "Unknown time rounding mode.");
  }
  return rounding;
}

function roundRational(numerator: bigint, denominator: bigint, rounding?: TimeRounding): bigint {
  rounding = validateRounding(rounding);
  if (denominator <= 0n) return fail("INVALID_TIME_VALUE", "Time conversion denominator must be positive.");
  let quotient = numerator / denominator;
  let remainder = numerator % denominator;
  if (remainder === 0n) return quotient;
  if (rounding === undefined) return fail("TIME_CONVERSION_INEXACT", "Select floor, ceil, or nearest_ties_to_even for this non-integral conversion.");
  if (remainder < 0n) {
    quotient -= 1n;
    remainder += denominator;
  }
  if (rounding === "floor") return quotient;
  if (rounding === "ceil") return quotient + 1n;
  const doubled = remainder * 2n;
  if (doubled < denominator) return quotient;
  if (doubled > denominator) return quotient + 1n;
  return quotient % 2n === 0n ? quotient : quotient + 1n;
}

function validateFrames(value: Frames | BoundFrames): Frames | BoundFrames {
  if (!knownFrames.has(value as object) && !knownBoundFrames.has(value as object)) return fail("INVALID_TIME_VALUE", "Frame quantity must come from frames().");
  return value;
}

function valueRate(value: Frames | BoundFrames): FrameRate | null {
  return knownBoundFrames.has(value as object) ? (value as BoundFrames).rate : null;
}

function compareFrames(left: Frames | BoundFrames, right: Frames | BoundFrames): number {
  validateFrames(right);
  const leftRate = valueRate(left);
  const rightRate = valueRate(right);
  if (leftRate && rightRate) requireMatchingRates(leftRate, rightRate);
  return left.value < right.value ? -1 : left.value > right.value ? 1 : 0;
}

function secondsFromFrames(value: number, rate: FrameRate, rounding?: TimeRounding): Seconds {
  const microseconds = roundRational(
    BigInt(value) * BigInt(rate.denominator) * MICROSECONDS_PER_SECOND,
    BigInt(rate.numerator),
    rounding,
  );
  return createSeconds(safeInteger(microseconds, "Seconds value"));
}

function framesFromSeconds(value: Seconds, rate: FrameRate, rounding?: TimeRounding): BoundFrames {
  const frameValue = roundRational(
    BigInt(value.microseconds) * BigInt(rate.numerator),
    MICROSECONDS_PER_SECOND * BigInt(rate.denominator),
    rounding,
  );
  return createBoundFrames(safeInteger(frameValue, "Frame value"), rate);
}

function createFrames(value: number): Frames {
  const quantity = {
    kind: "frames" as const,
    value,
    rate: null,
    bind(rate: FrameRate) { return createBoundFrames(value, validateRate(rate)); },
    compare(other: Frames) { return compareFrames(quantity as Frames, other); },
    eq(other: Frames) { return compareFrames(quantity as Frames, other) === 0; },
    lt(other: Frames) { return compareFrames(quantity as Frames, other) < 0; },
    lte(other: Frames) { return compareFrames(quantity as Frames, other) <= 0; },
    gt(other: Frames) { return compareFrames(quantity as Frames, other) > 0; },
    gte(other: Frames) { return compareFrames(quantity as Frames, other) >= 0; },
    add(other: Frames) { validateFrames(other); return frames(safeInteger(BigInt(value) + BigInt(other.value), "Frame sum")); },
    subtract(other: Frames) { validateFrames(other); return frames(safeInteger(BigInt(value) - BigInt(other.value), "Frame difference")); },
    toSeconds(rate: FrameRate, rounding?: TimeRounding) { return secondsFromFrames(value, validateRate(rate), rounding); },
    toJSON() { return { kind: "frames" as const, value }; },
    toString() { return `${value}fr`; },
  } as unknown as Frames;
  knownFrames.add(quantity as object);
  return Object.freeze(quantity);
}

function boundRational(other: Frames | BoundFrames | Seconds, rate: FrameRate): Rational {
  if (knownSeconds.has(other as object)) return secondsRational(other as Seconds);
  const frameValue = validateFrames(other as Frames | BoundFrames);
  const otherRate = valueRate(frameValue);
  if (otherRate) requireMatchingRates(rate, otherRate);
  return frameRational(frameValue.value, rate);
}

function createBoundFrames(value: number, rate: FrameRate): BoundFrames {
  const quantity = {
    kind: "frames" as const,
    value,
    rate,
    compare(other: Frames | BoundFrames | Seconds) { return compareRational(frameRational(value, rate), boundRational(other, rate)); },
    eq(other: Frames | BoundFrames | Seconds) { return quantity.compare(other) === 0; },
    lt(other: Frames | BoundFrames | Seconds) { return quantity.compare(other) < 0; },
    lte(other: Frames | BoundFrames | Seconds) { return quantity.compare(other) <= 0; },
    gt(other: Frames | BoundFrames | Seconds) { return quantity.compare(other) > 0; },
    gte(other: Frames | BoundFrames | Seconds) { return quantity.compare(other) >= 0; },
    add(other: Frames | BoundFrames | Seconds, rounding?: TimeRounding) {
      const delta = knownSeconds.has(other as object) ? framesFromSeconds(other as Seconds, rate, rounding).value : (validateFrames(other as Frames | BoundFrames), (other as Frames | BoundFrames).value);
      const otherRate = knownSeconds.has(other as object) ? null : valueRate(other as Frames | BoundFrames);
      if (otherRate) requireMatchingRates(rate, otherRate);
      return createBoundFrames(safeInteger(BigInt(value) + BigInt(delta), "Frame sum"), rate);
    },
    subtract(other: Frames | BoundFrames | Seconds, rounding?: TimeRounding) {
      const delta = knownSeconds.has(other as object) ? framesFromSeconds(other as Seconds, rate, rounding).value : (validateFrames(other as Frames | BoundFrames), (other as Frames | BoundFrames).value);
      const otherRate = knownSeconds.has(other as object) ? null : valueRate(other as Frames | BoundFrames);
      if (otherRate) requireMatchingRates(rate, otherRate);
      return createBoundFrames(safeInteger(BigInt(value) - BigInt(delta), "Frame difference"), rate);
    },
    toSeconds(rounding?: TimeRounding) { return secondsFromFrames(value, rate, rounding); },
    toJSON() { return { kind: "frames" as const, value, rate: rate.toJSON() }; },
    toString() { return `${value}fr@${rate.numerator}/${rate.denominator}`; },
  } as unknown as BoundFrames;
  knownBoundFrames.add(quantity as object);
  return Object.freeze(quantity);
}

/** Construct a safe integer rate-unbound frame quantity. @beta */
export function frames(value: number): Frames;
/** Construct a safe integer frame quantity bound to an authoritative rate. @beta */
export function frames(value: number, rate: FrameRate): BoundFrames;
export function frames(value: number, rate?: FrameRate): Frames | BoundFrames {
  if (!Number.isSafeInteger(value)) return fail("INVALID_TIME_VALUE", "Frames must be a safe integer.");
  return rate === undefined ? createFrames(value) : createBoundFrames(value, validateRate(rate));
}

function decimalFromNumber(value: number): string {
  if (!Number.isFinite(value)) return fail("INVALID_TIME_VALUE", "Seconds must be finite.");
  const raw = String(value);
  if (!/[eE]/.test(raw)) return raw;
  const match = /^(-?)(\d+)(?:\.(\d+))?[eE]([+-]?\d+)$/.exec(raw);
  if (!match) return fail("INVALID_TIME_VALUE", "Seconds number cannot be normalized.");
  const sign = match[1] ?? "";
  const whole = match[2] ?? "0";
  const fraction = match[3] ?? "";
  const exponent = Number(match[4]);
  const digits = `${whole}${fraction}`;
  const point = whole.length + exponent;
  if (point <= 0) return `${sign}0.${"0".repeat(-point)}${digits}`;
  if (point >= digits.length) return `${sign}${digits}${"0".repeat(point - digits.length)}`;
  return `${sign}${digits.slice(0, point)}.${digits.slice(point)}`;
}

function parseMicroseconds(value: number | string): number {
  const decimal = typeof value === "number" ? decimalFromNumber(value) : value;
  if (typeof decimal !== "string" || !/^-?\d+(?:\.\d{1,6})?$/.test(decimal)) {
    return fail("INVALID_TIME_VALUE", "Seconds must be a plain decimal with at most six fractional digits.");
  }
  const negative = decimal.startsWith("-");
  const unsigned = negative ? decimal.slice(1) : decimal;
  const [whole = "0", fraction = ""] = unsigned.split(".");
  const microseconds = BigInt(whole) * MICROSECONDS_PER_SECOND + BigInt(fraction.padEnd(6, "0"));
  return safeInteger(negative ? -microseconds : microseconds, "Seconds value");
}

function secondsComparison(left: Seconds, other: Seconds | Frames | BoundFrames, explicitRate?: FrameRate): number {
  const suppliedRate = explicitRate === undefined ? undefined : validateRate(explicitRate);
  if (knownSeconds.has(other as object)) return compareRational(secondsRational(left), secondsRational(other as Seconds));
  const frameValue = validateFrames(other as Frames | BoundFrames);
  const boundRate = valueRate(frameValue);
  const rate = boundRate ?? suppliedRate ?? fail("FRAME_RATE_REQUIRED", "A frame rate is required for cross-unit comparison.");
  if (boundRate && suppliedRate) requireMatchingRates(boundRate, suppliedRate);
  return compareRational(secondsRational(left), frameRational(frameValue.value, rate));
}

function createSeconds(microseconds: number): Seconds {
  const quantity = {
    kind: "seconds" as const,
    microseconds,
    compare(other: Seconds | Frames | BoundFrames, rate?: FrameRate) { return secondsComparison(quantity as Seconds, other, rate); },
    eq(other: Seconds | Frames | BoundFrames, rate?: FrameRate) { return secondsComparison(quantity as Seconds, other, rate) === 0; },
    lt(other: Seconds | Frames | BoundFrames, rate?: FrameRate) { return secondsComparison(quantity as Seconds, other, rate) < 0; },
    lte(other: Seconds | Frames | BoundFrames, rate?: FrameRate) { return secondsComparison(quantity as Seconds, other, rate) <= 0; },
    gt(other: Seconds | Frames | BoundFrames, rate?: FrameRate) { return secondsComparison(quantity as Seconds, other, rate) > 0; },
    gte(other: Seconds | Frames | BoundFrames, rate?: FrameRate) { return secondsComparison(quantity as Seconds, other, rate) >= 0; },
    add(other: Seconds) {
      if (!knownSeconds.has(other as object)) return fail("INVALID_TIME_VALUE", "Seconds arithmetic requires seconds().");
      return createSeconds(safeInteger(BigInt(microseconds) + BigInt(other.microseconds), "Seconds sum"));
    },
    subtract(other: Seconds) {
      if (!knownSeconds.has(other as object)) return fail("INVALID_TIME_VALUE", "Seconds arithmetic requires seconds().");
      return createSeconds(safeInteger(BigInt(microseconds) - BigInt(other.microseconds), "Seconds difference"));
    },
    toFrames(rate: FrameRate, rounding?: TimeRounding) { return framesFromSeconds(quantity as Seconds, validateRate(rate), rounding); },
    toJSON() { return { kind: "seconds" as const, microseconds }; },
    toString() {
      const sign = microseconds < 0 ? "-" : "";
      const absolute = Math.abs(microseconds);
      const whole = Math.floor(absolute / 1_000_000);
      const fraction = String(absolute % 1_000_000).padStart(6, "0").replace(/0+$/, "");
      return `${sign}${whole}${fraction ? `.${fraction}` : ""}s`;
    },
  } as unknown as Seconds;
  knownSeconds.add(quantity as object);
  return Object.freeze(quantity);
}

/** Construct exact decimal seconds with at most six fractional digits. @beta */
export function seconds(value: number | string): Seconds {
  return createSeconds(parseMicroseconds(value));
}

function isDropFrameRate(rate: FrameRate): boolean {
  return (rate.numerator === 30_000 && rate.denominator === 1001 && rate.nominalTimebase === 30)
    || (rate.numerator === 60_000 && rate.denominator === 1001 && rate.nominalTimebase === 60);
}

function timecodeFrameCount(label: string, rate: FrameRate, dropFrame: boolean): number {
  const match = TIMECODE_PATTERN.exec(label);
  if (!match) return fail("INVALID_TIME_VALUE", "Timecode must use HH:MM:SS:FF or HH:MM:SS;FF.");
  const hoursText = match[1];
  const minutesText = match[2];
  const secondsText = match[3];
  const separator = match[4];
  const framesText = match[5];
  if (!hoursText || !minutesText || !secondsText || !separator || !framesText) return fail("INVALID_TIME_VALUE", "Timecode label is incomplete.");
  const width = Math.max(2, String(rate.nominalTimebase - 1).length);
  if (framesText.length !== width) return fail("INVALID_TIME_VALUE", `Timecode frame field must contain exactly ${width} digits.`);
  const hours = Number(hoursText);
  const minutes = Number(minutesText);
  const second = Number(secondsText);
  const frame = Number(framesText);
  if (!Number.isSafeInteger(hours) || frame >= rate.nominalTimebase) return fail("INVALID_TIME_VALUE", "Timecode field is outside its valid range.");
  if (dropFrame !== (separator === ";")) return fail("INVALID_TIME_VALUE", "Timecode separator and drop-frame mode disagree.");
  if (dropFrame && !isDropFrameRate(rate)) return fail("INVALID_TIME_VALUE", "Drop-frame labels require 30000/1001 or 60000/1001.");
  const droppedPerMinute = rate.nominalTimebase === 60 ? 4 : 2;
  if (dropFrame && minutes % 10 !== 0 && second === 0 && frame < droppedPerMinute) return fail("INVALID_TIME_VALUE", "This label is skipped by drop-frame numbering.");
  const totalMinutes = BigInt(hours) * 60n + BigInt(minutes);
  let total = (BigInt(hours) * 3600n + BigInt(minutes) * 60n + BigInt(second)) * BigInt(rate.nominalTimebase) + BigInt(frame);
  if (dropFrame) total -= BigInt(droppedPerMinute) * (totalMinutes - totalMinutes / 10n);
  return safeInteger(total, "Timecode frame value");
}

function createTimecode(label: string, rate: FrameRate, dropFrame: boolean): Timecode {
  timecodeFrameCount(label, rate, dropFrame);
  const result = {
    kind: "timecode" as const,
    value: label,
    rate,
    dropFrame,
    equals(other: Timecode) { return knownTimecodes.has(other as object) && label === other.value && dropFrame === other.dropFrame && ratesEqual(rate, other.rate); },
    toFrames() { return createBoundFrames(timecodeFrameCount(label, rate, dropFrame), rate); },
    toJSON() { return { kind: "timecode" as const, value: label, rate: rate.toJSON(), dropFrame }; },
    toString() { return label; },
  } as unknown as Timecode;
  knownTimecodes.add(result as object);
  return Object.freeze(result);
}

/** Construct a validated timecode label carrying its exact rate. @beta */
export function timecode(value: string, rate: FrameRate, dropFrame?: boolean): Timecode {
  if (typeof value !== "string") return fail("INVALID_TIME_VALUE", "Timecode label must be a string.");
  if (dropFrame !== undefined && typeof dropFrame !== "boolean") return fail("INVALID_TIME_VALUE", "Drop-frame mode must be boolean.");
  return createTimecode(value, validateRate(rate), dropFrame ?? value.includes(";"));
}

/** Convert timecode to its bijective frame count at the same exact rate. @beta */
export function timecodeToFrames(value: Timecode, expectedRate?: FrameRate): BoundFrames {
  if (!knownTimecodes.has(value as object)) return fail("INVALID_TIME_VALUE", "Timecode must come from timecode().");
  requireMatchingRates(value.rate, expectedRate === undefined ? value.rate : validateRate(expectedRate));
  return value.toFrames();
}

function formatTimecodeFrame(frameValue: number, rate: FrameRate, dropFrame: boolean): string {
  if (frameValue < 0) return fail("INVALID_TIME_VALUE", "Timecode cannot represent a negative frame position.");
  let labelFrames = BigInt(frameValue);
  if (dropFrame) {
    if (!isDropFrameRate(rate)) return fail("INVALID_TIME_VALUE", "Drop-frame labels require 30000/1001 or 60000/1001.");
    const drop = BigInt(rate.nominalTimebase === 60 ? 4 : 2);
    const nominal = BigInt(rate.nominalTimebase);
    const framesPer10Minutes = nominal * 600n - drop * 9n;
    const framesPerMinute = nominal * 60n - drop;
    const blocks = labelFrames / framesPer10Minutes;
    const remainder = labelFrames % framesPer10Minutes;
    labelFrames += drop * 9n * blocks;
    if (remainder >= drop) labelFrames += drop * ((remainder - drop) / framesPerMinute);
  }
  const nominal = BigInt(rate.nominalTimebase);
  const hours = labelFrames / (nominal * 3600n);
  const minutes = (labelFrames / (nominal * 60n)) % 60n;
  const second = (labelFrames / nominal) % 60n;
  const frame = labelFrames % nominal;
  const width = Math.max(2, String(rate.nominalTimebase - 1).length);
  return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${second.toString().padStart(2, "0")}${dropFrame ? ";" : ":"}${frame.toString().padStart(width, "0")}`;
}

/** Convert frames to a bijective timecode label at an exact rate. @beta */
export function framesToTimecode(value: Frames | BoundFrames, rate?: FrameRate, dropFrame = false): Timecode {
  validateFrames(value);
  if (typeof dropFrame !== "boolean") return fail("INVALID_TIME_VALUE", "Drop-frame mode must be boolean.");
  const boundRate = valueRate(value);
  const suppliedRate = rate === undefined ? undefined : validateRate(rate);
  const effectiveRate = boundRate ?? suppliedRate ?? fail("FRAME_RATE_REQUIRED", "A frame rate is required to convert unbound frames to timecode.");
  if (boundRate && suppliedRate) requireMatchingRates(boundRate, suppliedRate);
  return createTimecode(formatTimecodeFrame(value.value, effectiveRate, dropFrame), effectiveRate, dropFrame);
}

function durationSeconds(value: Seconds | SecondsDuration): Seconds {
  if (knownSeconds.has(value as object)) return value as Seconds;
  if (knownDurations.has(value as object) && (value as Duration).unit === "seconds") return (value as SecondsDuration).value;
  return fail("INVALID_TIME_VALUE", "Expected a seconds duration.");
}

function durationFrames(value: Frames | BoundFrames | FrameDuration | BoundFrameDuration): Frames | BoundFrames {
  if (knownFrames.has(value as object) || knownBoundFrames.has(value as object)) return value as Frames | BoundFrames;
  if (knownDurations.has(value as object) && (value as Duration).unit === "frames") return (value as FrameDuration | BoundFrameDuration).value;
  return fail("INVALID_TIME_VALUE", "Expected a frame duration.");
}

function durationRational(value: unknown, explicitRate?: FrameRate): Rational {
  if (knownSeconds.has(value as object) || (knownDurations.has(value as object) && (value as Duration).unit === "seconds")) {
    return secondsRational(durationSeconds(value as Seconds | SecondsDuration));
  }
  const frameValue = durationFrames(value as Frames | BoundFrames | FrameDuration | BoundFrameDuration);
  const boundRate = valueRate(frameValue);
  const suppliedRate = explicitRate === undefined ? undefined : validateRate(explicitRate);
  const rate = boundRate ?? suppliedRate ?? fail("FRAME_RATE_REQUIRED", "A frame rate is required for this duration operation.");
  if (boundRate && suppliedRate) requireMatchingRates(boundRate, suppliedRate);
  return frameRational(frameValue.value, rate);
}

function durationCompare(left: Duration, other: unknown, explicitRate?: FrameRate): number {
  const suppliedRate = explicitRate === undefined ? undefined : validateRate(explicitRate);
  const leftRate = left.unit === "frames" ? left.rate ?? suppliedRate : suppliedRate;
  return compareRational(durationRational(left, leftRate ?? undefined), durationRational(other, leftRate ?? undefined));
}

function comparisonMethods(holder: { value?: Duration }) {
  return {
    compare(other: unknown, rate?: FrameRate) { return durationCompare(holder.value!, other, rate); },
    eq(other: unknown, rate?: FrameRate) { return durationCompare(holder.value!, other, rate) === 0; },
    lt(other: unknown, rate?: FrameRate) { return durationCompare(holder.value!, other, rate) < 0; },
    lte(other: unknown, rate?: FrameRate) { return durationCompare(holder.value!, other, rate) <= 0; },
    gt(other: unknown, rate?: FrameRate) { return durationCompare(holder.value!, other, rate) > 0; },
    gte(other: unknown, rate?: FrameRate) { return durationCompare(holder.value!, other, rate) >= 0; },
  };
}

function nonNegative(value: number): void {
  if (value < 0) fail("INVALID_TIME_VALUE", "Duration cannot be negative.");
}

function createSecondsDuration(value: Seconds): SecondsDuration {
  nonNegative(value.microseconds);
  const holder: { value?: Duration } = {};
  const result = {
    domain: "duration" as const,
    unit: "seconds" as const,
    value,
    rate: null,
    ...comparisonMethods(holder),
    add(other: Seconds | SecondsDuration) { return createSecondsDuration(value.add(durationSeconds(other))); },
    subtract(other: Seconds | SecondsDuration) { return createSecondsDuration(value.subtract(durationSeconds(other))); },
    toFrames(rate: FrameRate, rounding?: TimeRounding) { return createBoundFrameDuration(value.toFrames(rate, rounding)); },
    toJSON() { return { domain: "duration" as const, value: value.toJSON() }; },
    toString() { return `duration(${value.toString()})`; },
  } as unknown as SecondsDuration;
  holder.value = result;
  knownDurations.add(result as object);
  return Object.freeze(result);
}

function createFrameDuration(value: Frames): FrameDuration {
  nonNegative(value.value);
  const holder: { value?: Duration } = {};
  const result = {
    domain: "duration" as const,
    unit: "frames" as const,
    value,
    rate: null,
    ...comparisonMethods(holder),
    bind(rate: FrameRate) { return createBoundFrameDuration(value.bind(rate)); },
    add(other: Frames | FrameDuration) {
      const delta = durationFrames(other);
      if (knownBoundFrames.has(delta as object)) fail("FRAME_RATE_MISMATCH", "A bound frame duration cannot be added to an unbound duration.");
      return createFrameDuration(value.add(delta as Frames));
    },
    subtract(other: Frames | FrameDuration) {
      const delta = durationFrames(other);
      if (knownBoundFrames.has(delta as object)) fail("FRAME_RATE_MISMATCH", "A bound frame duration cannot be subtracted from an unbound duration.");
      return createFrameDuration(value.subtract(delta as Frames));
    },
    toJSON() { return { domain: "duration" as const, value: value.toJSON() }; },
    toString() { return `duration(${value.toString()})`; },
  } as unknown as FrameDuration;
  holder.value = result;
  knownDurations.add(result as object);
  return Object.freeze(result);
}

function createBoundFrameDuration(value: BoundFrames): BoundFrameDuration {
  nonNegative(value.value);
  const holder: { value?: Duration } = {};
  const result = {
    domain: "duration" as const,
    unit: "frames" as const,
    value,
    rate: value.rate,
    ...comparisonMethods(holder),
    add(other: Frames | BoundFrames | FrameDuration | BoundFrameDuration | Seconds | SecondsDuration, rounding?: TimeRounding) {
      const delta = knownSeconds.has(other as object) || (knownDurations.has(other as object) && (other as Duration).unit === "seconds")
        ? durationSeconds(other as Seconds | SecondsDuration)
        : durationFrames(other as Frames | BoundFrames | FrameDuration | BoundFrameDuration);
      return createBoundFrameDuration(value.add(delta as never, rounding));
    },
    subtract(other: Frames | BoundFrames | FrameDuration | BoundFrameDuration | Seconds | SecondsDuration, rounding?: TimeRounding) {
      const delta = knownSeconds.has(other as object) || (knownDurations.has(other as object) && (other as Duration).unit === "seconds")
        ? durationSeconds(other as Seconds | SecondsDuration)
        : durationFrames(other as Frames | BoundFrames | FrameDuration | BoundFrameDuration);
      return createBoundFrameDuration(value.subtract(delta as never, rounding));
    },
    toSeconds(rounding?: TimeRounding) { return value.toSeconds(rounding); },
    toJSON() { return { domain: "duration" as const, value: value.toJSON() }; },
    toString() { return `duration(${value.toString()})`; },
  } as unknown as BoundFrameDuration;
  holder.value = result;
  knownDurations.add(result as object);
  return Object.freeze(result);
}

/** Construct a non-negative seconds duration. @beta */
export function duration(value: Seconds): SecondsDuration;
/** Construct a non-negative rate-unbound frame duration. @beta */
export function duration(value: Frames): FrameDuration;
/** Construct a non-negative rate-bound frame duration. @beta */
export function duration(value: BoundFrames): BoundFrameDuration;
/** Construct a non-negative frame duration with an authoritative rate. @beta */
export function duration(value: Frames, rate: FrameRate): BoundFrameDuration;
export function duration(value: DurationInput, rate?: FrameRate): Duration {
  const suppliedRate = rate === undefined ? undefined : validateRate(rate);
  if (knownSeconds.has(value as object)) {
    if (suppliedRate) fail("INVALID_TIME_VALUE", "Seconds durations do not accept a frame-rate argument.");
    return createSecondsDuration(value as Seconds);
  }
  const frameValue = validateFrames(value as Frames | BoundFrames);
  if (knownBoundFrames.has(frameValue as object)) {
    if (suppliedRate) requireMatchingRates((frameValue as BoundFrames).rate, suppliedRate);
    return createBoundFrameDuration(frameValue as BoundFrames);
  }
  return suppliedRate ? createBoundFrameDuration((frameValue as Frames).bind(suppliedRate)) : createFrameDuration(frameValue as Frames);
}

function bindPosition(value: PositionValue, explicitRate?: FrameRate): PositionValue {
  const suppliedRate = explicitRate === undefined ? undefined : validateRate(explicitRate);
  if (knownSeconds.has(value as object)) {
    return value;
  }
  if (knownTimecodes.has(value as object)) {
    if (suppliedRate) requireMatchingRates((value as Timecode).rate, suppliedRate);
    return value;
  }
  const frameValue = validateFrames(value as Frames | BoundFrames);
  if (knownBoundFrames.has(frameValue as object)) {
    if (suppliedRate) requireMatchingRates((frameValue as BoundFrames).rate, suppliedRate);
    return frameValue;
  }
  return suppliedRate ? (frameValue as Frames).bind(suppliedRate) : frameValue;
}

function positionRate(value: PositionValue): FrameRate | null {
  if (knownSeconds.has(value as object)) return null;
  return knownTimecodes.has(value as object) ? (value as Timecode).rate : valueRate(value as Frames | BoundFrames);
}

/** Construct a position in the timeline-record domain. @beta */
export function timelineRecordPosition<Value extends PositionValue>(
  value: Value,
  rate?: FrameRate,
): TimelineRecordPositionOf<Value extends Frames ? Frames | BoundFrames : Value>;
export function timelineRecordPosition(value: PositionValue, rate?: FrameRate): TimelineRecordPosition {
  const bound = bindPosition(value, rate);
  const result = {
    domain: "timeline_record" as const,
    value: bound,
    rate: positionRate(bound) ?? (rate === undefined ? null : validateRate(rate)),
    toJSON() { return { domain: "timeline_record" as const, value: bound.toJSON() }; },
    toString() { return `record(${bound.toString()})`; },
  } as unknown as TimelineRecordPosition;
  knownTimelinePositions.add(result as object);
  return Object.freeze(result);
}

/** Construct a position in a media-source domain. @beta */
export function sourcePosition<Value extends PositionValue>(
  value: Value,
  rate?: FrameRate,
): SourcePositionOf<Value extends Frames ? Frames | BoundFrames : Value>;
export function sourcePosition(value: PositionValue, rate?: FrameRate): SourcePosition {
  const bound = bindPosition(value, rate);
  const result = {
    domain: "source" as const,
    value: bound,
    rate: positionRate(bound) ?? (rate === undefined ? null : validateRate(rate)),
    toJSON() { return { domain: "source" as const, value: bound.toJSON() }; },
    toString() { return `source(${bound.toString()})`; },
  } as unknown as SourcePosition;
  knownSourcePositions.add(result as object);
  return Object.freeze(result);
}

function rangeRateAndOrder(start: PositionValue, end: PositionValue, explicitRate?: FrameRate): FrameRate | null {
  const startRate = positionRate(start);
  const endRate = positionRate(end);
  if (startRate && endRate) requireMatchingRates(startRate, endRate);
  const rate = startRate ?? endRate ?? explicitRate ?? null;
  if (explicitRate !== undefined && rate) requireMatchingRates(rate, validateRate(explicitRate));
  const startIsPlainFrames = knownFrames.has(start as object);
  const endIsPlainFrames = knownFrames.has(end as object);
  if (!rate && startIsPlainFrames && endIsPlainFrames) {
    if ((start as Frames).value >= (end as Frames).value) {
      fail("INVALID_TIME_VALUE", "Half-open range end must be after its start.");
    }
    return null;
  }
  const rational = (value: PositionValue): Rational => {
    if (knownSeconds.has(value as object)) return secondsRational(value as Seconds);
    const effectiveRate = rate ?? fail("FRAME_RATE_REQUIRED", "A frame rate is required for a mixed-unit range.");
    const frameValue = knownTimecodes.has(value as object) ? (value as Timecode).toFrames().value : (value as Frames | BoundFrames).value;
    return frameRational(frameValue, effectiveRate);
  };
  if (compareRational(rational(start), rational(end)) >= 0) fail("INVALID_TIME_VALUE", "Half-open range end must be after its start.");
  return rate;
}

function rangePositionRate(start: FrameRate | null, end: FrameRate | null, explicitRate?: FrameRate): FrameRate | undefined {
  if (start && end) requireMatchingRates(start, end);
  const inherited = start ?? end;
  if (explicitRate !== undefined) {
    const validated = validateRate(explicitRate);
    if (inherited) requireMatchingRates(inherited, validated);
    return validated;
  }
  return inherited ?? undefined;
}

/** Construct a half-open timeline-record range from positions or position values. @beta */
export function timelineRecordRange<Start extends PositionValue, End extends PositionValue>(
  start: Start,
  endExclusive: End,
  rate?: FrameRate,
): TimelineRecordRangeOf<
  (Start extends Frames ? Frames | BoundFrames : Start)
  | (End extends Frames ? Frames | BoundFrames : End)
>;
/** Construct a range from already domain-bound timeline-record positions. @beta */
export function timelineRecordRange<Start extends PositionValue, End extends PositionValue>(
  start: TimelineRecordPositionOf<Start>,
  endExclusive: TimelineRecordPositionOf<End>,
  rate?: FrameRate,
): TimelineRecordRangeOf<Start | End>;
export function timelineRecordRange(
  start: TimelineRecordPosition | PositionValue,
  endExclusive: TimelineRecordPosition | PositionValue,
  rate?: FrameRate,
): TimelineRecordRange {
  const startPosition = knownTimelinePositions.has(start as object) ? start as TimelineRecordPosition : timelineRecordPosition(start as PositionValue, rate);
  const endPosition = knownTimelinePositions.has(endExclusive as object) ? endExclusive as TimelineRecordPosition : timelineRecordPosition(endExclusive as PositionValue, rate);
  const rangeRate = rangeRateAndOrder(
    startPosition.value,
    endPosition.value,
    rangePositionRate(startPosition.rate, endPosition.rate, rate),
  );
  const result = {
    domain: "timeline_record_range" as const,
    start: startPosition,
    endExclusive: endPosition,
    rate: rangeRate,
    toJSON() { return { domain: "timeline_record_range" as const, start: startPosition.toJSON(), endExclusive: endPosition.toJSON() }; },
    toString() { return `[${startPosition.toString()}, ${endPosition.toString()})`; },
  } as unknown as TimelineRecordRange;
  knownTimelineRanges.add(result as object);
  return Object.freeze(result);
}

/** Construct a half-open media-source range from positions or position values. @beta */
export function sourceRange<Start extends PositionValue, End extends PositionValue>(
  start: Start,
  endExclusive: End,
  rate?: FrameRate,
): SourceRangeOf<
  (Start extends Frames ? Frames | BoundFrames : Start)
  | (End extends Frames ? Frames | BoundFrames : End)
>;
/** Construct a range from already domain-bound source positions. @beta */
export function sourceRange<Start extends PositionValue, End extends PositionValue>(
  start: SourcePositionOf<Start>,
  endExclusive: SourcePositionOf<End>,
  rate?: FrameRate,
): SourceRangeOf<Start | End>;
export function sourceRange(
  start: SourcePosition | PositionValue,
  endExclusive: SourcePosition | PositionValue,
  rate?: FrameRate,
): SourceRange {
  const startPosition = knownSourcePositions.has(start as object) ? start as SourcePosition : sourcePosition(start as PositionValue, rate);
  const endPosition = knownSourcePositions.has(endExclusive as object) ? endExclusive as SourcePosition : sourcePosition(endExclusive as PositionValue, rate);
  const rangeRate = rangeRateAndOrder(
    startPosition.value,
    endPosition.value,
    rangePositionRate(startPosition.rate, endPosition.rate, rate),
  );
  const result = {
    domain: "source_range" as const,
    start: startPosition,
    endExclusive: endPosition,
    rate: rangeRate,
    toJSON() { return { domain: "source_range" as const, start: startPosition.toJSON(), endExclusive: endPosition.toJSON() }; },
    toString() { return `[${startPosition.toString()}, ${endPosition.toString()})`; },
  } as unknown as SourceRange;
  knownSourceRanges.add(result as object);
  return Object.freeze(result);
}

/** Internal identity checks used exclusively by the public wire adapter. @internal */
export const authoringTimeInternals = Object.freeze({
  isFrameRate: (value: unknown): value is FrameRate => typeof value === "object" && value !== null && knownRates.has(value),
  isFrames: (value: unknown): value is Frames | BoundFrames => typeof value === "object" && value !== null && (knownFrames.has(value) || knownBoundFrames.has(value)),
  isSeconds: (value: unknown): value is Seconds => typeof value === "object" && value !== null && knownSeconds.has(value),
  isTimecode: (value: unknown): value is Timecode => typeof value === "object" && value !== null && knownTimecodes.has(value),
  isDuration: (value: unknown): value is Duration => typeof value === "object" && value !== null && knownDurations.has(value),
  isTimelineRecordPosition: (value: unknown): value is TimelineRecordPosition => typeof value === "object" && value !== null && knownTimelinePositions.has(value),
  isSourcePosition: (value: unknown): value is SourcePosition => typeof value === "object" && value !== null && knownSourcePositions.has(value),
  isTimelineRecordRange: (value: unknown): value is TimelineRecordRange => typeof value === "object" && value !== null && knownTimelineRanges.has(value),
  isSourceRange: (value: unknown): value is SourceRange => typeof value === "object" && value !== null && knownSourceRanges.has(value),
  createSecondsFromMicroseconds: createSeconds,
});
