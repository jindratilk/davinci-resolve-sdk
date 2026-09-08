/** Stable synchronous authoring-value failure codes. @beta */
export type CutAgentValueErrorCode =
  | "INVALID_TIME_VALUE"
  | "FRAME_RATE_REQUIRED"
  | "FRAME_RATE_MISMATCH"
  | "TIME_CONVERSION_INEXACT"
  | "TIME_VALUE_OUT_OF_RANGE";

/** Local authoring failure raised before any carrier or runtime request. @beta */
export class CutAgentValueError extends Error {
  readonly code: CutAgentValueErrorCode;

  constructor(code: CutAgentValueErrorCode, message: string) {
    super(message);
    this.name = "CutAgentValueError";
    this.code = code;
    Object.freeze(this);
  }
}
