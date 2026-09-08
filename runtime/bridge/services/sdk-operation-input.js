import crypto from "node:crypto";

export function canonicalSdkOperationInput(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("SDK operation input numbers must be finite.");
    return Object.is(value, -0) ? 0 : value;
  }
  if (Array.isArray(value)) return value.map(canonicalSdkOperationInput);
  if (value && typeof value === "object") {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new TypeError("SDK operation inputs must contain only JSON objects.");
    }
    const output = {};
    for (const key of Object.keys(value).sort()) {
      if (value[key] === undefined) throw new TypeError("SDK operation inputs cannot contain undefined values.");
      output[key] = canonicalSdkOperationInput(value[key]);
    }
    return output;
  }
  throw new TypeError("SDK operation inputs must be JSON values.");
}

export function sdkOperationInputDigest(value) {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
}
