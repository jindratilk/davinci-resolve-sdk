import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {ensureCanonicalPrivateDirectory, writePrivateJsonDurableAtomic} from "./private-storage.js";

const ACCOUNT = /^[A-Za-z0-9_-]{20,128}$/u;
const OPERATION = /^operation_[A-Za-z0-9._~-]+$/u;
const NAMESPACE_DIGEST = /^sha256:[a-f0-9]{64}$/u;

function digest(value) {
  return `revision_${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("base64url")}`;
}
function identity(stat) { return {device: String(stat.dev), inode: String(stat.ino)}; }
function sameIdentity(left, right) { return left?.device === right?.device && left?.inode === right?.inode; }
function pathEntryExists(value) {
  try { fs.lstatSync(value); return true; } catch (error) { if (error?.code === "ENOENT") return false; throw error; }
}
function readState(statePath) {
  if (!fs.existsSync(statePath)) return {version: 1, destinations: {}};
  const value = JSON.parse(fs.readFileSync(statePath, "utf8"));
  if (value?.version !== 1 || !value.destinations || typeof value.destinations !== "object" || Array.isArray(value.destinations)) {
    throw new Error("SDK project-library destination registry is malformed.");
  }
  return value;
}

/** Durable authority for live DaVinci Resolve Disk Project Library destinations. */
export function createSdkProjectLibraryDestinationService({storageDir, writableRoots} = {}) {
  if (typeof storageDir !== "string" || !path.isAbsolute(storageDir) || !Array.isArray(writableRoots)) {
    throw new TypeError("Project-library destination custody requires private storage and granted roots.");
  }
  const store = ensureCanonicalPrivateDirectory(storageDir, {label: "Project-library destination registry"});
  const roots = writableRoots.filter((root) => fs.existsSync(root)).map((root) => {
    if (typeof root !== "string" || !path.isAbsolute(root)) throw new TypeError("Project-library writable roots must be absolute.");
    const canonicalPath = fs.realpathSync(root);
    const stat = fs.lstatSync(canonicalPath);
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error("Project-library writable root is not a canonical directory.");
    return {canonicalPath, identity: identity(stat), managedRootId: digest([canonicalPath, identity(stat)]).replace("revision_", "library_root_")};
  });
  const statePath = path.join(store, "project-library-destinations.json");
  const state = readState(statePath);
  const persist = () => writePrivateJsonDurableAtomic(statePath, state);

  const validateAbsent = (record) => {
    const parent = fs.realpathSync(record.canonicalParentPath);
    if (parent !== record.canonicalParentPath) throw new Error("Project-library destination parent changed canonical identity.");
    const stat = fs.lstatSync(parent);
    if (!stat.isDirectory() || stat.isSymbolicLink() || !sameIdentity(identity(stat), record.parentIdentity)) {
      throw new Error("Project-library destination parent identity changed.");
    }
    if (pathEntryExists(record.canonicalFinalPath)) throw new Error("Project-library destination is no longer absent.");
    return record;
  };

  return Object.freeze({
    reserve({operationId, accountFingerprint, libraryName, directoryPath, namespaceRevision}) {
      if (!OPERATION.test(operationId ?? "") || !ACCOUNT.test(accountFingerprint ?? "")
        || typeof libraryName !== "string" || !libraryName.trim() || !NAMESPACE_DIGEST.test(namespaceRevision ?? "")
        || typeof directoryPath !== "string" || !path.isAbsolute(directoryPath)) {
        throw new TypeError("Project-library destination reservation is invalid.");
      }
      const requestedFinalPath = path.resolve(directoryPath);
      const requestedParentPath = path.dirname(requestedFinalPath);
      const leafName = path.basename(requestedFinalPath);
      if (!leafName || leafName === "." || leafName === "..") throw new Error("Project-library destination leaf is invalid.");
      let parentPath;
      try { parentPath = fs.realpathSync(requestedParentPath); } catch { parentPath = requestedParentPath; }
      const root = roots.find((candidate) => candidate.canonicalPath === parentPath);
      if (!root) throw new Error("Project-library destination must be an immediate child of a granted writable root.");
      const finalPath = path.join(parentPath, leafName);
      const parentStat = fs.lstatSync(parentPath);
      if (!parentStat.isDirectory() || parentStat.isSymbolicLink() || fs.realpathSync(parentPath) !== root.canonicalPath
        || !sameIdentity(identity(parentStat), root.identity)) throw new Error("Project-library destination root identity changed.");
      const libraryDestinationId = digest([accountFingerprint, root.managedRootId, leafName]).replace("revision_", "project_library_destination_");
      const absenceRevision = digest({managedRootId: root.managedRootId, parentIdentity: root.identity, leafName, namespaceRevision, state: "absent"});
      const record = {libraryDestinationId, operationId, accountFingerprint, libraryName: libraryName.trim(), managedRootId: root.managedRootId,
        canonicalRootPath: root.canonicalPath, canonicalParentPath: parentPath, parentIdentity: root.identity, leafName,
        canonicalFinalPath: finalPath, namespaceRevision, absenceRevision, state: "reserved"};
      const existing = state.destinations[libraryDestinationId];
      if (existing) {
        if (JSON.stringify(existing) !== JSON.stringify(record)) throw new Error("Project-library destination ownership changed or is already active.");
        return Object.freeze(validateAbsent(structuredClone(existing)));
      }
      if (Object.values(state.destinations).some((value) => value.canonicalFinalPath === finalPath)) {
        throw new Error("Project-library destination is already reserved.");
      }
      validateAbsent(record);
      state.destinations[libraryDestinationId] = record;
      persist();
      return Object.freeze(structuredClone(record));
    },
    revalidate(record) {
      const stored = state.destinations[record?.libraryDestinationId];
      if (!stored || JSON.stringify(stored) !== JSON.stringify(record) || stored.state !== "reserved") {
        throw new Error("Project-library destination custody changed.");
      }
      return Object.freeze(structuredClone(validateAbsent(stored)));
    },
    settleTerminal({operationId, accountFingerprint, terminal}) {
      const records = Object.values(state.destinations).filter((record) => record.operationId === operationId && record.accountFingerprint === accountFingerprint);
      for (const record of records) {
        if (record.state !== "reserved") continue;
        if (terminal?.status === "succeeded" && terminal?.verification?.outcome === "passed") {
          try {
            const parentStat = fs.lstatSync(record.canonicalParentPath);
            const stat = fs.lstatSync(record.canonicalFinalPath);
            if (!sameIdentity(identity(parentStat), record.parentIdentity) || parentStat.isSymbolicLink() || !parentStat.isDirectory()
              || !stat.isDirectory() || stat.isSymbolicLink()
              || fs.realpathSync(path.dirname(record.canonicalFinalPath)) !== record.canonicalParentPath) {
              throw new Error("Verified Project Library destination has an invalid native identity.");
            }
            record.state = "active";
            record.finalIdentity = identity(stat);
            record.activationRevision = digest({absenceRevision: record.absenceRevision, finalIdentity: record.finalIdentity, libraryName: record.libraryName});
          } catch (error) {
            record.state = "uncertain";
            persist();
            throw error;
          }
        } else if (!pathEntryExists(record.canonicalFinalPath)) {
          delete state.destinations[record.libraryDestinationId];
        } else {
          record.state = "uncertain";
        }
      }
      if (records.length) persist();
    },
  });
}
