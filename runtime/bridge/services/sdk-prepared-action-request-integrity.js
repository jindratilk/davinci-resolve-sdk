import crypto from "node:crypto";
import {PRIVATE_IMPACT_REGISTRY_DIGEST} from "./mutation-policy/private-impact-registry.generated.js";

function canonical(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("Prepared-action request numbers must be finite.");
    return Object.is(value, -0) ? 0 : value;
  }
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => {
      if (value[key] === undefined) throw new TypeError("Prepared-action request values cannot be undefined.");
      return [key, canonical(value[key])];
    }));
  }
  throw new TypeError("Prepared-action request must be JSON-compatible.");
}

export function preparedActionRequestDigest(value) {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(canonical(value)), "utf8").digest("hex")}`;
}

export {PRIVATE_IMPACT_REGISTRY_DIGEST};
