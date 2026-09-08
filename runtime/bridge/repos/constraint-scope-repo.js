import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
  CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION,
  sdkConstraintScopeSchema,
} from "../contracts/generated/sdk-mutation-policy.js";
import {
  assertCanonicalPrivateDirectory,
  ensureCanonicalPrivateDirectory,
  writePrivateJsonDurableAtomic,
} from "../services/private-storage.js";

const STATE_VERSION = 1;
const INSTALLATION_AUTHORITY_PATTERN = /^constraint_installation_[A-Za-z0-9._~-]+$/;

function newState() {
  return {
    version: STATE_VERSION,
    installationAuthority: `constraint_installation_${crypto.randomUUID()}`,
    scopes: {},
    owners: {},
  };
}

function load(filePath) {
  if (!fs.existsSync(filePath)) return newState();
  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    throw new Error("Durable editing-constraint state is unreadable; refusing to discard user policy.", { cause: error });
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)
    || raw.version !== STATE_VERSION
    || !INSTALLATION_AUTHORITY_PATTERN.test(raw.installationAuthority ?? "")
    || !raw.scopes || typeof raw.scopes !== "object" || Array.isArray(raw.scopes)) {
    throw new Error("Durable editing-constraint state is incompatible or malformed.");
  }
  const scopes = Object.fromEntries(Object.entries(raw.scopes).map(([scopeId, value]) => {
    const scope = sdkConstraintScopeSchema.parse(value);
    if (scope.scopeId !== scopeId) throw new Error(`Constraint scope key mismatch: ${scopeId}`);
    return [scopeId, scope];
  }));
  const owners = raw.owners === undefined ? {} : raw.owners;
  if (!owners || typeof owners !== "object" || Array.isArray(owners)) {
    throw new Error("Durable editing-constraint owner index is malformed.");
  }
  for (const [ownerKey, scopeId] of Object.entries(owners)) {
    if (!/^scope_owner_[a-f0-9]{64}$/.test(ownerKey) || typeof scopeId !== "string" || !scopes[scopeId]) {
      throw new Error("Durable editing-constraint owner index is corrupt.");
    }
  }
  return { ...raw, scopes, owners };
}

function sameStableBinding(left, right) {
  return left.level === right.level
    && left.projectLibraryId === right.projectLibraryId
    && (left.level === "account/project-library" || left.projectId === right.projectId)
    && (left.level !== "project+timeline" || left.timelineId === right.timelineId);
}

/** Durable, fail-closed CAS store for normalized user-owned constraint scopes. */
export function createConstraintScopeRepo({ storageDir }) {
  if (typeof storageDir !== "string" || !storageDir.trim()) {
    throw new Error("createConstraintScopeRepo requires a storageDir.");
  }
  const directory = ensureCanonicalPrivateDirectory(storageDir, {
    label: "editing-constraint storage directory",
  });
  const filePath = path.join(directory, "mutation-policy-scopes-v1.json");
  const lockPath = path.join(directory, "mutation-policy-scopes-v1.lock");
  const pause = new Int32Array(new SharedArrayBuffer(4));

  function withLock(callback) {
    let descriptor;
    for (let attempt = 0; attempt < 400; attempt += 1) {
      try {
        descriptor = fs.openSync(lockPath, "wx", 0o600);
        fs.writeFileSync(descriptor, `${process.pid}\n`, "utf8");
        fs.fsyncSync(descriptor);
        break;
      } catch (error) {
        if (error?.code !== "EEXIST") throw error;
        try {
          const owner = Number(fs.readFileSync(lockPath, "utf8").trim());
          if (Number.isSafeInteger(owner) && owner > 0) {
            try { process.kill(owner, 0); } catch (probeError) {
              if (probeError?.code === "ESRCH") { fs.unlinkSync(lockPath); continue; }
            }
          } else if (Date.now() - fs.statSync(lockPath).mtimeMs > 1_000) {
            fs.unlinkSync(lockPath);
            continue;
          }
        } catch (inspectionError) {
          if (inspectionError?.code === "ENOENT") continue;
        }
        Atomics.wait(pause, 0, 0, 5);
      }
    }
    if (descriptor === undefined) throw new Error("Editing-constraint storage lock timed out.");
    try { return callback(); } finally {
      fs.closeSync(descriptor);
      fs.unlinkSync(lockPath);
    }
  }

  let state = withLock(() => {
    const current = load(filePath);
    if (!fs.existsSync(filePath)) writePrivateJsonDurableAtomic(filePath, current);
    return current;
  });

  function refresh() { state = load(filePath); return state; }

  function commit(next) {
    assertCanonicalPrivateDirectory(directory, { label: "editing-constraint storage directory" });
    writePrivateJsonDurableAtomic(filePath, next);
    state = next;
  }

  return Object.freeze({
    get installationAuthority() { return refresh().installationAuthority; },
    get(scopeId) {
      const scope = refresh().scopes[scopeId];
      return scope ? structuredClone(scope) : null;
    },
    listForAccount(accountFingerprint) {
      return Object.values(refresh().scopes)
        .filter((scope) => scope.accountFingerprint === accountFingerprint)
        .map((scope) => structuredClone(scope));
    },
    create(scope) {
      const validated = sdkConstraintScopeSchema.parse(scope);
      withLock(() => {
        refresh();
        if (state.scopes[validated.scopeId]) throw new Error("Constraint scope identity collision.");
        const next = structuredClone(state);
        next.scopes[validated.scopeId] = validated;
        commit(next);
      });
      return structuredClone(validated);
    },
    reconcileOwnedScope({ ownerKey, accountFingerprint, binding, defaultConstraints, nowIso }) {
      if (!/^scope_owner_[a-f0-9]{64}$/.test(ownerKey)) throw new Error("Constraint owner key is malformed.");
      return withLock(() => {
        refresh();
        const existingScopeId = state.owners[ownerKey];
        if (existingScopeId) {
          const current = state.scopes[existingScopeId];
          if (!current || current.accountFingerprint !== accountFingerprint || !sameStableBinding(current.binding, binding)) {
            throw new Error("Durable editing-constraint owner binding is corrupt.");
          }
          if (JSON.stringify(current.binding) === JSON.stringify(binding)) return structuredClone(current);
          const replacement = sdkConstraintScopeSchema.parse({
            ...current,
            revision: current.revision + 1,
            binding,
            updatedAt: nowIso,
          });
          const next = structuredClone(state);
          next.scopes[existingScopeId] = replacement;
          commit(next);
          return structuredClone(replacement);
        }
        const created = sdkConstraintScopeSchema.parse({
          contractVersion: CUTAGENT_MUTATION_POLICY_CONTRACT_VERSION,
          scopeId: `constraint_scope_${crypto.randomUUID()}`,
          accountFingerprint,
          revision: 1,
          binding,
          constraints: defaultConstraints,
          createdAt: nowIso,
          updatedAt: nowIso,
        });
        const next = structuredClone(state);
        next.scopes[created.scopeId] = created;
        next.owners[ownerKey] = created.scopeId;
        commit(next);
        return structuredClone(created);
      });
    },
    compareAndSwap(scopeId, expectedRevision, replacement) {
      return withLock(() => {
        refresh();
        const current = state.scopes[scopeId];
        if (!current) return null;
        if (current.revision !== expectedRevision) return false;
        const validated = sdkConstraintScopeSchema.parse(replacement);
        if (validated.scopeId !== scopeId
          || validated.accountFingerprint !== current.accountFingerprint
          || validated.createdAt !== current.createdAt
          || validated.revision !== current.revision + 1) {
          throw new Error("Constraint scope CAS replacement violates immutable ownership or revision ordering.");
        }
        const next = structuredClone(state);
        next.scopes[scopeId] = validated;
        commit(next);
        return structuredClone(validated);
      });
    },
    inspect() { return structuredClone(refresh()); },
  });
}
