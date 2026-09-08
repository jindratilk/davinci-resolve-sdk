import crypto from "node:crypto";

const LABELS = new Set([
  "account", "subscription", "session", "action", "input", "contract", "capability", "protocol",
  "app-artifact", "runtime-artifact", "cli-artifact", "packaged-ancestry", "project", "timeline",
  "targets", "pre-state", "impact", "policy-decision", "receipt", "execution", "idempotency",
  "prepared-runtime-identities", "prepared-runtime-revisions",
]);

function normalized(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("Prepared-action digest numbers must be finite.");
    if (Object.is(value, -0) || value === 0) return 0;
    if (Number.isSafeInteger(value)) return value;
    const bytes = Buffer.allocUnsafe(8);
    bytes.writeDoubleBE(value);
    return { $cutagentFloat64: bytes.toString("hex") };
  }
  if (Array.isArray(value)) return value.map(normalized);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalized(value[key])]));
  }
  throw new TypeError("Prepared-action digest input must be canonical JSON.");
}

export function canonicalPreparedActionBytes(value) {
  return Buffer.from(JSON.stringify(normalized(value)), "utf8");
}

export function preparedActionDigest(label, value) {
  if (!LABELS.has(label)) throw new TypeError("Prepared-action digest label is unknown.");
  return `sha256:${crypto.createHash("sha256")
    .update(Buffer.concat([
      Buffer.from(`cutagent-sdk-prepared-action-v1\0${label}\0`, "utf8"),
      canonicalPreparedActionBytes(value),
    ]))
    .digest("hex")}`;
}
