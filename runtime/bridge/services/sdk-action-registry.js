const registryOwnership = new WeakMap();
const LOW_LEVEL_RESULT_PROJECTION = "cutagent.sdk.low_level_read.result.v1";

export function mergeSdkActionRegistries(registries) {
  const merged = Object.create(null);
  const owners = new Map();
  for (const { owner, actions } of registries) {
    if (typeof owner !== "string" || owner.length === 0 || actions === null || typeof actions !== "object" || Array.isArray(actions)) {
      throw new TypeError("Each SDK action registry requires a named owner and an action record.");
    }
    for (const [actionId, definition] of Object.entries(actions)) {
      const previous = owners.get(actionId);
      if (previous) {
        throw new Error(`Duplicate SDK action owner for ${actionId}: ${previous}, ${owner}`);
      }
      owners.set(actionId, owner);
      merged[actionId] = definition;
    }
  }
  const frozen = Object.freeze(merged);
  registryOwnership.set(frozen, Object.freeze(Object.fromEntries(owners)));
  return frozen;
}

function requireRegistry(registry) {
  const { owner, actions } = registry ?? {};
  if (typeof owner !== "string" || owner.length === 0 || actions === null || typeof actions !== "object" || Array.isArray(actions)) {
    throw new TypeError("Each SDK action registry requires a named owner and an action record.");
  }
  return {owner, actions, nestedOwnership: registryOwnership.get(actions) ?? null};
}

/** Resolve the complete candidate graph without allowing implicit shadowing. */
export function resolveSdkActionRegistries(registries) {
  if (!Array.isArray(registries)) throw new TypeError("SDK action ownership resolution requires registries.");
  const candidates = new Map();
  for (const registry of registries) {
    const {owner, actions, nestedOwnership} = requireRegistry(registry);
    for (const [actionId, definition] of Object.entries(actions)) {
      const effectiveCandidateOwner = nestedOwnership?.[actionId] ?? owner;
      if (!definition || typeof definition !== "object"
        || typeof definition.inputSchema?.parse !== "function"
        || typeof definition.resultSchema?.parse !== "function"
        || typeof definition.execute !== "function") {
        throw new TypeError(`SDK action owner ${effectiveCandidateOwner} has an incomplete definition: ${actionId}`);
      }
      const entries = candidates.get(actionId) ?? [];
      if (entries.some((entry) => entry.owner === effectiveCandidateOwner)) {
        throw new Error(`SDK action owner registered the same action twice: ${effectiveCandidateOwner}:${actionId}`);
      }
      entries.push(Object.freeze({
        owner: effectiveCandidateOwner,
        definition,
        publicResultProjection: effectiveCandidateOwner === "typed_low_level"
          ? LOW_LEVEL_RESULT_PROJECTION
          : `${actionId}.result`,
      }));
      candidates.set(actionId, entries);
    }
  }

  const resolved = Object.create(null);
  const ownership = Object.create(null);
  const failures = [];
  for (const actionId of [...candidates.keys()].sort()) {
    const entries = candidates.get(actionId);
    if (entries.length !== 1) {
      failures.push(`${actionId}: multiple effective owners ${entries.map((entry) => entry.owner).join(",")}`);
      continue;
    }
    resolved[actionId] = entries[0].definition;
    ownership[actionId] = Object.freeze({
      effectiveOwner: entries[0].owner,
      publicResultProjection: entries[0].publicResultProjection,
    });
  }
  if (failures.length > 0) {
    throw new Error(`SDK effective-owner graph is invalid:\n${failures.join("\n")}`);
  }
  return Object.freeze({actions: Object.freeze(resolved), ownership: Object.freeze(ownership)});
}
