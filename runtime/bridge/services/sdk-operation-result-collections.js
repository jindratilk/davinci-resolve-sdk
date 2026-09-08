import crypto from "node:crypto";
import { canonicalSdkOperationInput } from "./sdk-operation-input.js";

export const SDK_OPERATION_RESULT_COLLECTION_MAX_ITEMS = 10_000;
export const SDK_OPERATION_RESULT_COLLECTION_MAX_BYTES = 6 * 1024 * 1024;
export const SDK_OPERATION_RESULT_COLLECTION_DEFAULT_PAGE_SIZE = 128;

const EDIT_RESULT_COLLECTIONS = Object.freeze({
  "cutagent.action.edit.auto_subtitle": [{ collectionId: "details.createdCaptions", path: ["details", "createdCaptions", "completeItems"], kind: "identity_map" }],
  "cutagent.action.edit.from_edl": [{ collectionId: "details.importedItems", path: ["details", "importedItems", "completeItems"], kind: "identity_map" }],
  "cutagent.action.edit.remove": [{ collectionId: "details.removedItems", path: ["details", "removedItems", "completeItems"], kind: "identity_map" }],
  "cutagent.action.edit.remove_range": [{ collectionId: "details.removedItems", path: ["details", "removedItems", "completeItems"], kind: "identity_map" }],
  "cutagent.action.edit.ripple_delete": [{ collectionId: "details.removedItems", path: ["details", "removedItems", "completeItems"], kind: "identity_map" }],
  "cutagent.action.edit.ripple_delete_selected": [{ collectionId: "details.removedItems", path: ["details", "removedItems", "completeItems"], kind: "identity_map" }],
  "cutagent.action.edit.scene_detect": [{ collectionId: "details.sourceItems", path: ["details", "sourceItems", "completeCuts"], kind: "array" }],
  "cutagent.action.edit.social_crop": [{ collectionId: "details.transformedItems", path: ["details", "transformedItems", "completeItems"], kind: "identity_map" }],
});

function digest(kind, entries) {
  const canonical = JSON.stringify(canonicalSdkOperationInput({ kind, entries }));
  return `sha256:${crypto.createHash("sha256").update(canonical, "utf8").digest("hex")}`;
}

function parentAt(result, path) {
  let current = result;
  for (const key of path.slice(0, -1)) {
    if (!current || typeof current !== "object" || Array.isArray(current) || !Object.hasOwn(current, key)) {
      throw new Error(`SDK result collection path is missing: ${path.join(".")}`);
    }
    current = current[key];
  }
  return { parent: current, key: path.at(-1) };
}

function materialize(spec, value) {
  let entries;
  if (spec.kind === "identity_map") {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Identity-map result collection is malformed.");
    entries = Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, entryValue]) => ({ key, value: canonicalSdkOperationInput(entryValue) }));
  } else {
    if (!Array.isArray(value)) throw new Error("Array result collection is malformed.");
    entries = value.map((entryValue, index) => ({ index, value: canonicalSdkOperationInput(entryValue) }));
  }
  if (entries.length > SDK_OPERATION_RESULT_COLLECTION_MAX_ITEMS) {
    throw new Error("SDK result collection exceeds its item bound.");
  }
  if (Buffer.byteLength(JSON.stringify(entries), "utf8") > SDK_OPERATION_RESULT_COLLECTION_MAX_BYTES) {
    throw new Error("SDK result collection exceeds its durable byte bound.");
  }
  const collectionDigest = digest(spec.kind, entries);
  return {
    durable: { kind: spec.kind, digest: collectionDigest, entries },
    reference: {
      collectionId: spec.collectionId,
      kind: spec.kind,
      totalItems: entries.length,
      digest: collectionDigest,
      defaultPageSize: SDK_OPERATION_RESULT_COLLECTION_DEFAULT_PAGE_SIZE,
    },
  };
}

export function editResultCollectionSpecs(actionId) {
  return EDIT_RESULT_COLLECTIONS[actionId]?.map((entry) => ({ ...entry, path: [...entry.path] })) ?? [];
}

export function projectSdkOperationResultCollections(result, specs = []) {
  const projected = canonicalSdkOperationInput(result);
  if (!Array.isArray(specs) || specs.length > 8) throw new Error("SDK result collection declarations are malformed.");
  const collections = {};
  for (const spec of specs) {
    if (!spec || !["identity_map", "array"].includes(spec.kind)
      || typeof spec.collectionId !== "string" || !/^[A-Za-z][A-Za-z0-9_.-]{0,159}$/.test(spec.collectionId)
      || !Array.isArray(spec.path) || spec.path.length < 2 || spec.path.some((part) => typeof part !== "string" || !part)) {
      throw new Error("SDK result collection declaration is malformed.");
    }
    if (Object.hasOwn(collections, spec.collectionId)) throw new Error("SDK result collection identity is duplicated.");
    const { parent, key } = parentAt(projected, spec.path);
    const { durable, reference } = materialize(spec, parent[key]);
    if (Object.hasOwn(parent, "resultPage")) throw new Error("SDK executor cannot supply an authority-owned result page reference.");
    parent.resultPage = reference;
    collections[spec.collectionId] = durable;
  }
  return { result: canonicalSdkOperationInput(projected), collections };
}

export function sdkOperationResultCollectionDigest(kind, entries) {
  return digest(kind, entries);
}
