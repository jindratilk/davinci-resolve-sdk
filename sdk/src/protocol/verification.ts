import type { z } from "zod";
import {
  sdkEvidenceModalitySchema,
  sdkVerificationEvidenceSchema,
  sdkVerificationOutcomeSchema,
  sdkVerificationReportSchema,
} from "../generated/sdk-operations.js";
import type { ArtifactId, EvidenceId } from "../value-types/identities.js";

/** Verification result independent of how evidence was collected. @beta */
export type VerificationOutcome = "passed" | "failed" | "partial" | "not_performed" | "manual_review_required";
/** Verification result independent of how evidence was collected. @beta */
export const VerificationOutcomeSchema: z.ZodType<VerificationOutcome> = sdkVerificationOutcomeSchema;
/** Sanitized evidence modality independent of verification outcome. @beta */
export type EvidenceModality = "readback" | "structural" | "file" | "rendered" | "visual" | "auditioned";
/** Sanitized evidence modality independent of verification outcome. @beta */
export const EvidenceModalitySchema: z.ZodType<EvidenceModality> = sdkEvidenceModalitySchema;
/** Public verification evidence without local paths or private traces. @beta */
export interface VerificationEvidence {
  evidenceId: EvidenceId;
  modality: EvidenceModality;
  summary: string;
  capturedAt: string;
  artifactId?: ArtifactId;
  digest?: string;
}
/** Public verification evidence without local paths or private traces. @beta */
export const VerificationEvidenceSchema = sdkVerificationEvidenceSchema as unknown as z.ZodType<VerificationEvidence>;
/** Structured verification report. Outcome and modalities are intentionally separate. @beta */
export interface VerificationReport {
  outcome: VerificationOutcome;
  summary: string;
  evidence: VerificationEvidence[];
  protectedStatePreserved: boolean | null;
}
/** Structured verification report. @beta */
export const VerificationReportSchema = sdkVerificationReportSchema as unknown as z.ZodType<VerificationReport>;
