import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
  sdkArtifactContentChunkSchema,
} from "../contracts/generated/sdk-runtime.js";
import {
  sdkArtifactIdSchema,
  sdkOperationIdSchema,
} from "../contracts/generated/sdk-identities.js";
import {
  assertCanonicalPrivateDirectory,
  ensureCanonicalPrivateDirectory,
  writePrivateJsonDurableAtomic,
} from "./private-storage.js";
import {
  DEFAULT_SDK_IDEMPOTENCY_TOMBSTONE_MS,
  DEFAULT_SDK_RESULT_RETENTION_MS,
} from "./sdk-operation-authority.js";

const STATE_VERSION = 1;
const ACCOUNT_FINGERPRINT_PATTERN = /^[A-Za-z0-9_-]{20,128}$/;
const SHA256_PATTERN = /^sha256:[a-f0-9]{64}$/;
const MAX_CHUNK_BYTES = 1024 * 1024;
const MAX_PRIVATE_DIRECTORY_ENTRIES = 4096;
const MAX_PRIVATE_DIRECTORY_BYTES = 512 * 1024 * 1024;
const MAX_FUSION_SETTING_BYTES = 4 * 1024 * 1024;

function validateFusionSettingBytes(bytes) {
  if (!Buffer.isBuffer(bytes) || bytes.length < 1 || bytes.length > MAX_FUSION_SETTING_BYTES) {
    throw new TypeError("Fusion setting input must contain 1 through 4194304 bytes.");
  }
  let source;
  try { source = new TextDecoder("utf-8", {fatal: true}).decode(bytes); }
  catch { throw new TypeError("Fusion setting input must be valid UTF-8."); }
  if (/[^\x09\x0a\x0d\x20-\x7e\u0080-\uffff]/u.test(source)
    || !/^(?:\s|--[^\n]*(?:\n|$))*(?:Composition\s*)?\{/.test(source)
    || !/\bTools\s*=\s*(?:ordered\s*\(\s*\)\s*)?\{/.test(source) || !/\}\s*$/.test(source)) {
    throw new TypeError("Fusion setting input lacks a structured Tools table.");
  }
  const stack = []; let quote = null; let escaped = false; let lineComment = false;
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index]; const next = source[index + 1];
    if (lineComment) { if (char === "\n") lineComment = false; continue; }
    if (quote) { if (escaped) escaped = false; else if (char === "\\") escaped = true; else if (char === quote) quote = null; continue; }
    if (char === "-" && next === "-") { lineComment = true; index += 1; continue; }
    if (char === '"' || char === "'") { quote = char; continue; }
    if ("{[(".includes(char)) stack.push(char);
    else if ("}])".includes(char)) {
      const expected = char === "}" ? "{" : char === "]" ? "[" : "(";
      if (stack.pop() !== expected) throw new TypeError("Fusion setting input has unbalanced structure.");
    }
  }
  if (quote || stack.length) throw new TypeError("Fusion setting input has incomplete structure.");
}

function sha256Descriptor(descriptor, sizeBytes) {
  const hash = crypto.createHash("sha256");
  const buffer = Buffer.alloc(Math.min(MAX_CHUNK_BYTES, sizeBytes));
  let offset = 0;
  while (offset < sizeBytes) {
    const requested = Math.min(buffer.length, sizeBytes - offset);
    const bytesRead = fs.readSync(descriptor, buffer, 0, requested, offset);
    if (bytesRead !== requested) throw new Error("SDK artifact changed while its digest was being verified.");
    hash.update(buffer.subarray(0, bytesRead));
    offset += bytesRead;
  }
  return `sha256:${hash.digest("hex")}`;
}

function emptyState() {
  return { version: STATE_VERSION, artifacts: {}, reservations: {}, discarded: {} };
}

function validateDiscarded(record, artifactId) {
  if (!record || typeof record !== "object"
    || sdkArtifactIdSchema.safeParse(artifactId).success !== true
    || record.artifactId !== artifactId
    || sdkOperationIdSchema.safeParse(record.operationId).success !== true
    || !ACCOUNT_FINGERPRINT_PATTERN.test(record.accountFingerprint ?? "")
    || !SHA256_PATTERN.test(record.receiptSha256 ?? "")
    || !Number.isFinite(record.discardedAtMs) || !Number.isFinite(record.availableUntilMs)
    || record.availableUntilMs <= record.discardedAtMs) {
    throw new Error(`SDK discarded artifact record is malformed: ${artifactId}`);
  }
  return Object.freeze({...record});
}

function sameIdentity(stat, record) {
  return stat.isFile()
    && stat.dev === record.dev
    && stat.ino === record.ino
    && stat.size === record.sizeBytes
    && stat.mtimeMs === record.mtimeMs
    && stat.ctimeMs === record.ctimeMs;
}

function validateRecord(record, artifactId, root) {
  const kind = record?.kind ?? "file";
  if (!record || typeof record !== "object"
    || sdkArtifactIdSchema.safeParse(artifactId).success !== true
    || record.artifactId !== artifactId
    || sdkOperationIdSchema.safeParse(record.operationId).success !== true
    || !ACCOUNT_FINGERPRINT_PATTERN.test(record.accountFingerprint ?? "")
    || !SHA256_PATTERN.test(record.sha256 ?? "")
    || !Number.isSafeInteger(record.sizeBytes) || record.sizeBytes < 1
    || !Number.isFinite(record.dev) || !Number.isFinite(record.ino)
    || !Number.isFinite(record.mtimeMs) || !Number.isFinite(record.ctimeMs)
    || !Number.isFinite(record.resultExpiresAtMs) || !Number.isFinite(record.availableUntilMs)
    || record.availableUntilMs <= record.resultExpiresAtMs
    || typeof record.filePath !== "string" || !path.isAbsolute(record.filePath)
    || !["file", "directory"].includes(kind)
    || (kind === "directory" && (
      typeof record.directoryPath !== "string" || !path.isAbsolute(record.directoryPath)
      || !SHA256_PATTERN.test(record.treeDigest ?? "")
      || !Number.isSafeInteger(record.totalBytes) || record.totalBytes < 1
      || !record.directoryIdentity || !Number.isFinite(record.directoryIdentity.dev) || !Number.isFinite(record.directoryIdentity.ino)
      || !Number.isFinite(record.directoryIdentity.mtimeMs) || !Number.isFinite(record.directoryIdentity.ctimeMs)
      || !Array.isArray(record.directories) || !Array.isArray(record.directoryEntries) || !Array.isArray(record.entries)
    ))) {
    throw new Error(`SDK artifact record is malformed: ${artifactId}`);
  }
  for (const candidatePath of [record.filePath, ...(kind === "directory" ? [record.directoryPath] : [])]) {
    const relative = path.relative(root, candidatePath);
    if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
      throw new Error(`SDK artifact escaped its managed root: ${artifactId}`);
    }
  }
  return Object.freeze({ ...record, kind });
}

function validateReservation(record, artifactId, root) {
  const kind = record?.kind ?? "file";
  const purpose = record?.purpose ?? "private";
  if (!record || typeof record !== "object"
    || sdkArtifactIdSchema.safeParse(artifactId).success !== true
    || record.artifactId !== artifactId
    || sdkOperationIdSchema.safeParse(record.operationId).success !== true
    || !ACCOUNT_FINGERPRINT_PATTERN.test(record.accountFingerprint ?? "")
    || typeof record.filePath !== "string" || !path.isAbsolute(record.filePath)
    || !Number.isFinite(record.dev) || !Number.isFinite(record.ino)
    || !Number.isFinite(record.createdAtMs) || !Number.isFinite(record.availableUntilMs)
    || !["file", "directory"].includes(kind)
    || !["private", "output"].includes(purpose)) {
    throw new Error(`SDK artifact reservation is malformed: ${artifactId}`);
  }
  const relative = path.relative(root, record.filePath);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`SDK artifact reservation escaped its managed root: ${artifactId}`);
  }
  return Object.freeze({...record, kind, purpose});
}

function sameDirectoryIdentity(stat, record) {
  return stat.isDirectory() && !stat.isSymbolicLink()
    && stat.dev === record.dev && stat.ino === record.ino;
}

function privateDirectorySnapshot(directoryPath, reservation) {
  const rootBefore = fs.lstatSync(directoryPath);
  if (!sameDirectoryIdentity(rootBefore, reservation)) throw new Error("The managed directory identity is no longer available.");
  const entries = [];
  const directories = [];
  const directoryEntries = [];
  let totalBytes = 0;
  const visit = (current, relativeRoot) => {
    for (const name of fs.readdirSync(current).sort()) {
      const absolute = path.join(current, name);
      const relativePath = relativeRoot ? `${relativeRoot}/${name}` : name;
      if (Buffer.byteLength(relativePath, "utf8") > 4096) throw new Error("The managed directory path exceeded its bound.");
      const pathStat = fs.lstatSync(absolute);
      if (pathStat.isSymbolicLink()) throw new Error("The managed directory contains a symbolic link.");
      if (pathStat.isDirectory()) {
        directories.push(relativePath);
        directoryEntries.push(Object.freeze({
          relativePath,
          identity: Object.freeze({device: pathStat.dev, inode: pathStat.ino, mtimeMs: pathStat.mtimeMs, ctimeMs: pathStat.ctimeMs}),
        }));
        if (directories.length + entries.length > MAX_PRIVATE_DIRECTORY_ENTRIES) throw new Error("The managed directory entry count exceeded its bound.");
        visit(absolute, relativePath);
        const after = fs.lstatSync(absolute);
        if (!after.isDirectory() || after.isSymbolicLink() || after.dev !== pathStat.dev || after.ino !== pathStat.ino
          || after.mtimeMs !== pathStat.mtimeMs || after.ctimeMs !== pathStat.ctimeMs) {
          throw new Error("The managed directory changed during private capture.");
        }
        continue;
      }
      if (!pathStat.isFile()) throw new Error("The managed directory contains a special file.");
      if (directories.length + entries.length >= MAX_PRIVATE_DIRECTORY_ENTRIES) throw new Error("The managed directory entry count exceeded its bound.");
      totalBytes += pathStat.size;
      if (!Number.isSafeInteger(totalBytes) || totalBytes > MAX_PRIVATE_DIRECTORY_BYTES) throw new Error("The managed directory bytes exceeded their bound.");
      const descriptor = fs.openSync(absolute, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
      try {
        const opened = fs.fstatSync(descriptor);
        if (!opened.isFile() || opened.dev !== pathStat.dev || opened.ino !== pathStat.ino || opened.size !== pathStat.size) {
          throw new Error("The managed directory file identity changed.");
        }
        const sha256 = sha256Descriptor(descriptor, opened.size);
        const after = fs.fstatSync(descriptor);
        const afterPath = fs.lstatSync(absolute);
        if (!sameIdentity(after, {dev: opened.dev, ino: opened.ino, sizeBytes: opened.size, mtimeMs: opened.mtimeMs, ctimeMs: opened.ctimeMs})
          || afterPath.isSymbolicLink() || afterPath.dev !== opened.dev || afterPath.ino !== opened.ino
          || afterPath.size !== opened.size || afterPath.mtimeMs !== opened.mtimeMs || afterPath.ctimeMs !== opened.ctimeMs) {
          throw new Error("The managed directory file changed during private capture.");
        }
        entries.push(Object.freeze({
          relativePath, sizeBytes: opened.size, sha256,
          identity: Object.freeze({device: opened.dev, inode: opened.ino, mtimeMs: opened.mtimeMs, ctimeMs: opened.ctimeMs}),
        }));
      } finally { fs.closeSync(descriptor); }
    }
  };
  visit(directoryPath, "");
  const rootAfter = fs.lstatSync(directoryPath);
  if (!sameDirectoryIdentity(rootAfter, rootBefore) || rootAfter.mtimeMs !== rootBefore.mtimeMs || rootAfter.ctimeMs !== rootBefore.ctimeMs) {
    throw new Error("The managed directory changed during private capture.");
  }
  const manifest = {directoryEntries, entries};
  return {
    directories: Object.freeze(directories), directoryEntries: Object.freeze(directoryEntries),
    entries: Object.freeze(entries), totalBytes,
    treeDigest: `sha256:${crypto.createHash("sha256").update(JSON.stringify(manifest)).digest("hex")}`,
    identity: {device: rootBefore.dev, inode: rootBefore.ino, mtimeMs: rootBefore.mtimeMs, ctimeMs: rootBefore.ctimeMs},
  };
}

function materializeDirectoryBundle(directoryPath, snapshot, bundlePath) {
  const flags = fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_RDWR | (fs.constants.O_NOFOLLOW ?? 0);
  const output = fs.openSync(bundlePath, flags, 0o600);
  const hash = crypto.createHash("sha256");
  let sizeBytes = 0;
  const write = (buffer) => {
    let offset = 0;
    while (offset < buffer.length) {
      const written = fs.writeSync(output, buffer, offset, buffer.length - offset);
      if (written < 1) throw new Error("SDK directory artifact bundle write did not make progress.");
      hash.update(buffer.subarray(offset, offset + written));
      sizeBytes += written;
      offset += written;
    }
  };
  try {
    write(Buffer.from("CUTAGENT-DIRECTORY-ARTIFACT-V1\n", "utf8"));
    write(Buffer.from(`${JSON.stringify({
      directories: snapshot.directories,
      entries: snapshot.entries.map(({relativePath, sizeBytes: entrySize, sha256}) => ({relativePath, sizeBytes: entrySize, sha256})),
    })}\n`, "utf8"));
    for (const entry of snapshot.entries) {
      write(Buffer.from(`${JSON.stringify({relativePath: entry.relativePath, sizeBytes: entry.sizeBytes})}\n`, "utf8"));
      const sourcePath = path.join(directoryPath, ...entry.relativePath.split("/"));
      const descriptor = fs.openSync(sourcePath, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
      try {
        const before = fs.fstatSync(descriptor);
        const expected = {
          dev: entry.identity.device, ino: entry.identity.inode, sizeBytes: entry.sizeBytes,
          mtimeMs: entry.identity.mtimeMs, ctimeMs: entry.identity.ctimeMs,
        };
        if (!sameIdentity(before, expected)) throw new Error("SDK directory artifact changed before bundle publication.");
        const buffer = Buffer.alloc(Math.min(MAX_CHUNK_BYTES, entry.sizeBytes));
        let sourceOffset = 0;
        while (sourceOffset < entry.sizeBytes) {
          const requested = Math.min(buffer.length, entry.sizeBytes - sourceOffset);
          const bytesRead = fs.readSync(descriptor, buffer, 0, requested, sourceOffset);
          if (bytesRead !== requested) throw new Error("SDK directory artifact changed during bundle publication.");
          write(buffer.subarray(0, bytesRead));
          sourceOffset += bytesRead;
        }
        if (!sameIdentity(fs.fstatSync(descriptor), expected)) throw new Error("SDK directory artifact changed during bundle publication.");
      } finally {
        fs.closeSync(descriptor);
      }
      write(Buffer.from("\n", "utf8"));
    }
    fs.fsyncSync(output);
    const stat = fs.fstatSync(output);
    if (!stat.isFile() || stat.size !== sizeBytes) throw new Error("SDK directory artifact bundle identity is invalid.");
    return {stat, sizeBytes, sha256: `sha256:${hash.digest("hex")}`};
  } catch (error) {
    try { fs.closeSync(output); } catch { /* Best-effort close before removing an unpublished private bundle. */ }
    try { fs.unlinkSync(bundlePath); } catch { /* Preserve the original publication failure. */ }
    throw error;
  } finally {
    try { fs.closeSync(output); } catch { /* Descriptor may already be closed on failure. */ }
  }
}

function collectPublicArtifactDescriptors(value, found = []) {
  if (!value || typeof value !== "object") return found;
  if (!Array.isArray(value)) {
    const id = value.artifactId ?? value.id;
    const digest = value.sha256 ?? value.digest;
    const sizeBytes = value.sizeBytes ?? value.byteCount ?? value.byteLength;
    const canonicalDigest = /^[a-f0-9]{64}$/.test(digest ?? "") ? `sha256:${digest}` : digest;
    if (sdkArtifactIdSchema.safeParse(id).success) {
      if (SHA256_PATTERN.test(canonicalDigest ?? "")
        && (Number.isSafeInteger(sizeBytes) && sizeBytes > 0
          || sizeBytes == null && typeof value.mediaType === "string" && value.mediaType.length > 0)) {
        found.push({artifactId: id, sizeBytes, sha256: canonicalDigest});
      } else if (Number.isSafeInteger(sizeBytes) && sizeBytes > 0 && value.artifactId === id && digest == null) {
        found.push({artifactId: id, sizeBytes, sha256: null});
      }
    }
    const opaqueMatch = typeof value.outputPath === "string"
      ? /^cutagent-artifact:([^@]+)@[^@]+$/u.exec(value.outputPath) : null;
    if (opaqueMatch && sdkArtifactIdSchema.safeParse(opaqueMatch[1]).success
      && Number.isSafeInteger(value.byteCount) && value.byteCount > 0
      && !found.some((item) => item.artifactId === opaqueMatch[1])) {
      found.push({artifactId: opaqueMatch[1], sizeBytes: value.byteCount, sha256: null});
    }
  }
  for (const nested of Array.isArray(value) ? value : Object.values(value)) collectPublicArtifactDescriptors(nested, found);
  return found;
}

function collectPublicArtifactIds(value, found = new Set()) {
  if (!value || typeof value !== "object") return found;
  if (!Array.isArray(value)) {
    for (const [key, candidate] of Object.entries(value)) {
      if ((key === "artifactId" || key.endsWith("ArtifactId")) && sdkArtifactIdSchema.safeParse(candidate).success) {
        found.add(candidate);
      }
      if (key === "outputPath" && typeof candidate === "string") {
        const opaque = /^cutagent-artifact:([^@]+)@[^@]+$/u.exec(candidate);
        if (opaque && sdkArtifactIdSchema.safeParse(opaque[1]).success) found.add(opaque[1]);
      }
    }
  }
  for (const nested of Array.isArray(value) ? value : Object.values(value)) collectPublicArtifactIds(nested, found);
  return found;
}

function loadState(filePath, root) {
  if (!fs.existsSync(filePath)) return emptyState();
  const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (parsed?.version !== STATE_VERSION || !parsed.artifacts || typeof parsed.artifacts !== "object" || Array.isArray(parsed.artifacts)
    || (parsed.reservations !== undefined && (typeof parsed.reservations !== "object" || Array.isArray(parsed.reservations)))
    || (parsed.discarded !== undefined && (typeof parsed.discarded !== "object" || Array.isArray(parsed.discarded)))) {
    throw new Error("SDK artifact registry is malformed.");
  }
  return {
    version: STATE_VERSION,
    artifacts: Object.fromEntries(Object.entries(parsed.artifacts).map(([id, record]) => [id, validateRecord(record, id, root)])),
    reservations: Object.fromEntries(Object.entries(parsed.reservations ?? {}).map(([id, record]) => [id, validateReservation(record, id, root)])),
    discarded: Object.fromEntries(Object.entries(parsed.discarded ?? {}).map(([id, record]) => [id, validateDiscarded(record, id)])),
  };
}

export function createSdkArtifactService({
  storageDir,
  managedRenderRoot,
  now = () => Date.now(),
  resultRetentionMs = DEFAULT_SDK_RESULT_RETENTION_MS,
  artifactRetentionMs = DEFAULT_SDK_IDEMPOTENCY_TOMBSTONE_MS,
  cleanupIntervalMs = 60 * 60 * 1000,
} = {}) {
  if (typeof storageDir !== "string" || !path.isAbsolute(storageDir)
    || typeof managedRenderRoot !== "string" || !path.isAbsolute(managedRenderRoot)
    || typeof now !== "function"
    || !Number.isFinite(resultRetentionMs) || resultRetentionMs < 1
    || !Number.isFinite(artifactRetentionMs) || artifactRetentionMs <= resultRetentionMs
    || !Number.isFinite(cleanupIntervalMs) || cleanupIntervalMs < 1) {
    throw new TypeError("SDK artifact service requires absolute private paths and bounded retention.");
  }
  const store = fs.realpathSync(ensureCanonicalPrivateDirectory(storageDir, { label: "SDK artifact registry directory" }));
  const root = fs.realpathSync(ensureCanonicalPrivateDirectory(managedRenderRoot, { label: "Managed render root" }));
  const statePath = path.join(store, "sdk-artifacts.json");
  let state = loadState(statePath, root);

  const persist = () => writePrivateJsonDurableAtomic(statePath, state);
  const ownedArtifact = ({artifactId, operationId, accountFingerprint}) => {
    sdkArtifactIdSchema.parse(artifactId);
    sdkOperationIdSchema.parse(operationId);
    if (!ACCOUNT_FINGERPRINT_PATTERN.test(accountFingerprint ?? "")) throw new TypeError("SDK private artifact ownership is invalid.");
    const source = state.artifacts[artifactId] ?? state.reservations[artifactId];
    if (!source) {
      const error = new Error("The managed artifact is unavailable.");
      error.code = "TARGET_NOT_FOUND";
      throw error;
    }
    if (source.operationId !== operationId || source.accountFingerprint !== accountFingerprint) {
      throw new Error("SDK artifact operation ownership changed.");
    }
    return source;
  };
  const assertRecordFile = (record) => {
    assertCanonicalPrivateDirectory(path.dirname(record.filePath), { label: "Managed render operation directory" });
    const noFollow = Number.isInteger(fs.constants.O_NOFOLLOW) ? fs.constants.O_NOFOLLOW : 0;
    const descriptor = fs.openSync(record.filePath, fs.constants.O_RDONLY | noFollow);
    const stat = fs.fstatSync(descriptor);
    if (!sameIdentity(stat, record)) {
      fs.closeSync(descriptor);
      const error = new Error("The managed artifact identity is no longer available.");
      error.code = "TARGET_NOT_FOUND";
      throw error;
    }
    return descriptor;
  };
  const assertRecordDirectory = (record) => {
    if (record.kind !== "directory") throw new Error("The managed artifact is not a directory artifact.");
    assertCanonicalPrivateDirectory(path.dirname(record.directoryPath), {label: "Managed render operation directory"});
    const stat = fs.lstatSync(record.directoryPath);
    if (!sameDirectoryIdentity(stat, record.directoryIdentity)
      || stat.mtimeMs !== record.directoryIdentity.mtimeMs || stat.ctimeMs !== record.directoryIdentity.ctimeMs) {
      const error = new Error("The managed directory artifact identity is no longer available.");
      error.code = "TARGET_NOT_FOUND";
      throw error;
    }
    const snapshot = privateDirectorySnapshot(record.directoryPath, record.directoryIdentity);
    if (snapshot.treeDigest !== record.treeDigest || snapshot.totalBytes !== record.totalBytes
      || JSON.stringify(snapshot.directories) !== JSON.stringify(record.directories)
      || JSON.stringify(snapshot.directoryEntries) !== JSON.stringify(record.directoryEntries)
      || JSON.stringify(snapshot.entries) !== JSON.stringify(record.entries)) {
      const error = new Error("The managed directory artifact changed after publication.");
      error.code = "TARGET_NOT_FOUND";
      throw error;
    }
    return snapshot;
  };
  const cleanup = () => {
    const current = now();
    let changed = false;
    for (const [artifactId, record] of Object.entries(state.artifacts)) {
      if (record.availableUntilMs > current) continue;
      if (record.kind === "directory") {
        try {
          const directoryStat = fs.lstatSync(record.directoryPath);
          if (sameDirectoryIdentity(directoryStat, record.directoryIdentity)) fs.rmSync(record.directoryPath, {recursive: true, force: true});
        } catch (error) {
          if (error?.code !== "ENOENT") continue;
        }
      }
      try {
        const stat = fs.lstatSync(record.filePath);
        if (!stat.isSymbolicLink() && sameIdentity(stat, record)) fs.unlinkSync(record.filePath);
      } catch (error) {
        if (error?.code !== "ENOENT") continue;
      }
      try { fs.rmdirSync(path.dirname(record.filePath)); } catch { /* Preserve non-empty managed operation directories. */ }
      delete state.artifacts[artifactId];
      changed = true;
    }
    for (const [artifactId, reservation] of Object.entries(state.reservations)) {
      if (reservation.availableUntilMs > current || state.artifacts[artifactId]) continue;
      try {
        const stat = fs.lstatSync(reservation.filePath);
        if (!stat.isSymbolicLink() && stat.dev === reservation.dev && stat.ino === reservation.ino) {
          if (reservation.kind === "directory" && stat.isDirectory()) fs.rmSync(reservation.filePath, {recursive: true, force: true});
          else if (reservation.kind === "file" && stat.isFile()) fs.unlinkSync(reservation.filePath);
        }
      } catch (error) {
        if (error?.code !== "ENOENT") continue;
      }
      try { fs.rmdirSync(path.dirname(reservation.filePath)); } catch { /* Preserve non-empty managed operation directories. */ }
      delete state.reservations[artifactId];
      changed = true;
    }
    for (const [artifactId, discarded] of Object.entries(state.discarded)) {
      if (discarded.availableUntilMs > current) continue;
      delete state.discarded[artifactId];
      changed = true;
    }
    if (changed) persist();
    return changed;
  };
  const reservePrivateFile = ({artifactId, operationId, accountFingerprint, extension}, purpose) => {
    cleanup();
    sdkArtifactIdSchema.parse(artifactId);
    sdkOperationIdSchema.parse(operationId);
    if (!ACCOUNT_FINGERPRINT_PATTERN.test(accountFingerprint ?? "") || !/^[a-z0-9]{1,12}$/.test(extension ?? "")) {
      throw new TypeError("SDK artifact reservation ownership or extension is invalid.");
    }
    if (state.discarded[artifactId]) throw new Error("SDK artifact identity has a retained discard tombstone.");
    const existing = state.reservations[artifactId];
    if (existing) {
      if (existing.kind !== "file" || existing.purpose !== purpose
        || existing.operationId !== operationId || existing.accountFingerprint !== accountFingerprint) {
        throw new Error("SDK artifact reservation ownership changed.");
      }
      const stat = fs.lstatSync(existing.filePath);
      if (!stat.isFile() || stat.isSymbolicLink() || stat.dev !== existing.dev || stat.ino !== existing.ino) throw new Error("SDK artifact reservation identity changed.");
      return Object.freeze({artifactId, absolutePath: existing.filePath, identity: Object.freeze({device: existing.dev, inode: existing.ino})});
    }
    if (state.artifacts[artifactId]) throw new Error("SDK artifact is already published.");
    const operationDir = ensureCanonicalPrivateDirectory(path.join(root, operationId), {label: "Managed render operation directory"});
    const filePath = path.join(operationDir, `${artifactId}.${extension}`);
    const flags = fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_RDWR | (fs.constants.O_NOFOLLOW ?? 0);
    const descriptor = fs.openSync(filePath, flags, 0o600);
    try {
      const stat = fs.fstatSync(descriptor);
      if (!stat.isFile()) throw new Error("SDK artifact reservation is not a regular file.");
      const createdAtMs = now();
      state.reservations[artifactId] = validateReservation({
        artifactId, operationId, accountFingerprint, filePath, kind: "file", purpose,
        dev: stat.dev, ino: stat.ino, createdAtMs,
        availableUntilMs: createdAtMs + artifactRetentionMs,
      }, artifactId, root);
      persist();
      return Object.freeze({artifactId, absolutePath: filePath, identity: Object.freeze({device: stat.dev, inode: stat.ino})});
    } finally {
      fs.closeSync(descriptor);
    }
  };
  const reservePrivateDirectory = ({artifactId, operationId, accountFingerprint}, purpose) => {
    cleanup();
    sdkArtifactIdSchema.parse(artifactId);
    sdkOperationIdSchema.parse(operationId);
    if (!ACCOUNT_FINGERPRINT_PATTERN.test(accountFingerprint ?? "")) throw new TypeError("SDK directory artifact reservation ownership is invalid.");
    if (state.discarded[artifactId]) throw new Error("SDK artifact identity has a retained discard tombstone.");
    const existing = state.reservations[artifactId];
    if (existing) {
      if (existing.kind !== "directory" || existing.purpose !== purpose
        || existing.operationId !== operationId || existing.accountFingerprint !== accountFingerprint) {
        throw new Error("SDK directory artifact reservation ownership changed.");
      }
      const stat = fs.lstatSync(existing.filePath);
      if (!sameDirectoryIdentity(stat, existing)) throw new Error("SDK directory artifact reservation identity changed.");
      return Object.freeze({artifactId, absolutePath: existing.filePath, identity: Object.freeze({device: existing.dev, inode: existing.ino})});
    }
    if (state.artifacts[artifactId]) throw new Error("SDK artifact is already published.");
    const operationDir = ensureCanonicalPrivateDirectory(path.join(root, operationId), {label: "Managed render operation directory"});
    const directoryPath = path.join(operationDir, `${artifactId}.directory`);
    fs.mkdirSync(directoryPath, {mode: 0o700});
    const stat = fs.lstatSync(directoryPath);
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error("SDK directory artifact reservation is invalid.");
    const createdAtMs = now();
    state.reservations[artifactId] = validateReservation({
      artifactId, operationId, accountFingerprint, filePath: directoryPath, kind: "directory", purpose,
      dev: stat.dev, ino: stat.ino, mtimeMs: stat.mtimeMs, ctimeMs: stat.ctimeMs, createdAtMs,
      availableUntilMs: createdAtMs + artifactRetentionMs,
    }, artifactId, root);
    persist();
    return Object.freeze({artifactId, absolutePath: directoryPath, identity: Object.freeze({device: stat.dev, inode: stat.ino})});
  };
  cleanup();
  const timer = setInterval(cleanup, cleanupIntervalMs);
  timer.unref?.();

  return Object.freeze({
    publishFusionSetting({bytes, accountFingerprint}) {
      cleanup();
      validateFusionSettingBytes(bytes);
      if (!ACCOUNT_FINGERPRINT_PATTERN.test(accountFingerprint ?? "")) throw new TypeError("SDK Fusion setting ownership is invalid.");
      const identity = crypto.createHash("sha256").update(accountFingerprint).update("\0").update(bytes).digest("base64url");
      const artifactId = `artifact_fusion_setting_${identity}`;
      const operationId = `operation_fusion_setting_${identity}`;
      try {
        this.read({artifactId, accountFingerprint, offset: 0, length: 1});
        const existing = this.capturePrivateManagedArtifact({artifactId, accountFingerprint});
        return Object.freeze({artifactId, mediaType: "application/x-fusion-setting", byteCount: existing.sizeBytes, sha256: existing.sha256});
      } catch (error) {
        if (error?.code !== "TARGET_NOT_FOUND") throw error;
      }
      const reserved = reservePrivateFile({artifactId, operationId, accountFingerprint, extension: "setting"}, "private");
      const flags = fs.constants.O_WRONLY | (fs.constants.O_NOFOLLOW ?? 0);
      const descriptor = fs.openSync(reserved.absolutePath, flags);
      try {
        const stat = fs.fstatSync(descriptor);
        if (!stat.isFile() || stat.dev !== reserved.identity.device || stat.ino !== reserved.identity.inode) throw new Error("Fusion setting reservation identity changed.");
        let offset = 0;
        while (offset < bytes.length) {
          const written = fs.writeSync(descriptor, bytes, offset, bytes.length - offset, offset);
          if (written < 1) throw new Error("Fusion setting publication did not make progress.");
          offset += written;
        }
        fs.fsyncSync(descriptor);
      } finally { fs.closeSync(descriptor); }
      const sha256 = `sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`;
      this.register({artifactId, operationId, accountFingerprint, filePath: reserved.absolutePath, sizeBytes: bytes.length, sha256});
      return Object.freeze({artifactId, mediaType: "application/x-fusion-setting", byteCount: bytes.length, sha256});
    },
    privateArtifactStoreRoot({operationId, accountFingerprint}) {
      cleanup();
      sdkOperationIdSchema.parse(operationId);
      if (!ACCOUNT_FINGERPRINT_PATTERN.test(accountFingerprint ?? "")) throw new TypeError("SDK private artifact-store ownership is invalid.");
      return fs.realpathSync(ensureCanonicalPrivateDirectory(path.join(root, operationId), {label: "Managed render operation directory"}));
    },
    privateManagedRoot() {
      return root;
    },
    capturePrivateOutputReservations({operationId, accountFingerprint}) {
      cleanup();
      sdkOperationIdSchema.parse(operationId);
      if (!ACCOUNT_FINGERPRINT_PATTERN.test(accountFingerprint ?? "")) throw new TypeError("SDK output reservation ownership is invalid.");
      return Object.freeze(Object.values(state.reservations)
        .filter((reservation) => reservation.purpose === "output"
          && reservation.operationId === operationId
          && reservation.accountFingerprint === accountFingerprint
          && reservation.availableUntilMs > now())
        .sort((left, right) => left.artifactId.localeCompare(right.artifactId))
        .map((reservation) => Object.freeze({
          artifactId: reservation.artifactId,
          absolutePath: reservation.filePath,
          kind: reservation.kind,
          identity: Object.freeze({device: reservation.dev, inode: reservation.ino}),
        })));
    },
    capturePrivateOwnedArtifactReceipt({artifactId, operationId, accountFingerprint}) {
      cleanup();
      const source = ownedArtifact({artifactId, operationId, accountFingerprint});
      const captured = source.kind === "directory"
        ? this.capturePrivateManagedDirectory({artifactId, accountFingerprint})
        : this.capturePrivateManagedArtifact({artifactId, accountFingerprint});
      const evidence = source.kind === "directory"
        ? {
            artifactId, operationId, kind: "directory", treeDigest: captured.treeDigest,
            totalBytes: captured.totalBytes, directories: captured.directories,
            directoryEntries: captured.directoryEntries, entries: captured.entries,
            identity: captured.identity,
          }
        : {
            artifactId, operationId, kind: "file", sizeBytes: captured.sizeBytes,
            sha256: captured.sha256, identity: captured.identity,
          };
      return Object.freeze({...evidence, receiptSha256: `sha256:${crypto.createHash("sha256").update(JSON.stringify(evidence)).digest("hex")}`});
    },
    discardPrivateOwnedArtifact({artifactId, operationId, accountFingerprint, receiptSha256}) {
      cleanup();
      sdkArtifactIdSchema.parse(artifactId);
      sdkOperationIdSchema.parse(operationId);
      if (!ACCOUNT_FINGERPRINT_PATTERN.test(accountFingerprint ?? "") || !SHA256_PATTERN.test(receiptSha256 ?? "")) {
        throw new TypeError("SDK private artifact discard authority is invalid.");
      }
      const discarded = state.discarded[artifactId];
      if (discarded) {
        if (discarded.operationId !== operationId || discarded.accountFingerprint !== accountFingerprint
          || discarded.receiptSha256 !== receiptSha256) throw new Error("SDK discarded artifact ownership changed.");
        return Object.freeze({artifactId, operationId, cleaned: true, alreadyAbsent: true, receiptSha256});
      }
      const source = ownedArtifact({artifactId, operationId, accountFingerprint});
      const observed = this.capturePrivateOwnedArtifactReceipt({artifactId, operationId, accountFingerprint});
      if (observed.receiptSha256 !== receiptSha256) throw new Error("SDK artifact changed after evaluator observation.");
      const removeFile = (filePath, identity, label) => {
        const stat = fs.lstatSync(filePath);
        if (!stat.isFile() || stat.isSymbolicLink() || stat.dev !== identity.device || stat.ino !== identity.inode
          || (identity.sizeBytes !== undefined && stat.size !== identity.sizeBytes)
          || (identity.mtimeMs !== undefined && stat.mtimeMs !== identity.mtimeMs)
          || (identity.ctimeMs !== undefined && stat.ctimeMs !== identity.ctimeMs)) {
          throw new Error(`${label} identity changed before evaluator cleanup.`);
        }
        fs.unlinkSync(filePath);
        if (fs.existsSync(filePath)) throw new Error(`${label} remained after evaluator cleanup.`);
      };
      if (source.kind === "directory") {
        const directoryPath = source.directoryPath ?? source.filePath;
        const directoryStat = fs.lstatSync(directoryPath);
        if (!sameDirectoryIdentity(directoryStat, {dev: observed.identity.device, ino: observed.identity.inode})) {
          throw new Error("SDK directory artifact identity changed before evaluator cleanup.");
        }
        if (source.directoryPath) {
          const descriptor = assertRecordFile(source);
          fs.closeSync(descriptor);
        }
        fs.rmSync(directoryPath, {recursive: true, force: false});
        if (fs.existsSync(directoryPath)) throw new Error("SDK directory artifact remained after evaluator cleanup.");
        if (source.directoryPath) removeFile(source.filePath, {
          device: source.dev, inode: source.ino, sizeBytes: source.sizeBytes,
          mtimeMs: source.mtimeMs, ctimeMs: source.ctimeMs,
        }, "SDK directory bundle");
      } else {
        removeFile(source.filePath, {...observed.identity, sizeBytes: observed.sizeBytes}, "SDK file artifact");
      }
      const nextState = {...state, artifacts: {...state.artifacts}, reservations: {...state.reservations}, discarded: {...state.discarded}};
      delete nextState.artifacts[artifactId];
      delete nextState.reservations[artifactId];
      const discardedAtMs = now();
      nextState.discarded[artifactId] = validateDiscarded({
        artifactId, operationId, accountFingerprint, receiptSha256, discardedAtMs,
        availableUntilMs: discardedAtMs + artifactRetentionMs,
      }, artifactId);
      writePrivateJsonDurableAtomic(statePath, nextState);
      state = nextState;
      try { fs.rmdirSync(path.dirname(source.filePath)); } catch { /* Preserve non-empty managed operation directories. */ }
      return Object.freeze({artifactId, operationId, cleaned: true, alreadyAbsent: false, receiptSha256});
    },
    discardPrivateOwnedArtifactByOperation({artifactId, operationId, accountFingerprint}) {
      cleanup(); sdkArtifactIdSchema.parse(artifactId); sdkOperationIdSchema.parse(operationId);
      if (!ACCOUNT_FINGERPRINT_PATTERN.test(accountFingerprint ?? "")) throw new TypeError("SDK private artifact discard authority is invalid.");
      const discarded = state.discarded[artifactId];
      if (discarded) {
        if (discarded.operationId !== operationId || discarded.accountFingerprint !== accountFingerprint) throw new Error("SDK discarded artifact ownership changed.");
        return Object.freeze({artifactId, operationId, cleaned: true, alreadyAbsent: true, receiptSha256: discarded.receiptSha256});
      }
      const receipt = this.capturePrivateOwnedArtifactReceipt({artifactId, operationId, accountFingerprint});
      return this.discardPrivateOwnedArtifact({artifactId, operationId, accountFingerprint, receiptSha256: receipt.receiptSha256});
    },
    abortPrivateArtifactReservation({artifactId, operationId, accountFingerprint, identity}) {
      cleanup();
      sdkArtifactIdSchema.parse(artifactId);
      sdkOperationIdSchema.parse(operationId);
      if (!ACCOUNT_FINGERPRINT_PATTERN.test(accountFingerprint ?? "")
        || !identity || !Number.isSafeInteger(Number(identity.device)) || !Number.isSafeInteger(Number(identity.inode))) {
        throw new TypeError("SDK private artifact abort authority is invalid.");
      }
      const source = state.reservations[artifactId] ?? state.artifacts[artifactId];
      if (!source) return Object.freeze({artifactId, operationId, cleaned: true, alreadyAbsent: true});
      if (source.operationId !== operationId || source.accountFingerprint !== accountFingerprint
        || source.dev !== Number(identity.device) || source.ino !== Number(identity.inode) || source.kind === "directory") {
        throw new Error("SDK private artifact abort ownership changed.");
      }
      const stat = fs.lstatSync(source.filePath);
      if (!stat.isFile() || stat.isSymbolicLink() || stat.dev !== source.dev || stat.ino !== source.ino) {
        throw new Error("SDK private artifact abort identity changed.");
      }
      fs.unlinkSync(source.filePath);
      if (fs.existsSync(source.filePath)) throw new Error("SDK aborted artifact remained after cleanup.");
      const nextState = {...state, artifacts: {...state.artifacts}, reservations: {...state.reservations}};
      delete nextState.artifacts[artifactId];
      delete nextState.reservations[artifactId];
      writePrivateJsonDurableAtomic(statePath, nextState);
      state = nextState;
      try { fs.rmdirSync(path.dirname(source.filePath)); } catch { /* Preserve non-empty managed operation directories. */ }
      return Object.freeze({artifactId, operationId, cleaned: true, alreadyAbsent: false});
    },
    publishPrivateOutputArtifacts({operationId, accountFingerprint, publicResult}) {
      const reservations = this.capturePrivateOutputReservations({operationId, accountFingerprint});
      const publicDescriptors = collectPublicArtifactDescriptors(publicResult);
      const publicDescriptorIds = new Set(publicDescriptors.map(({artifactId}) => artifactId));
      const publicArtifactIds = collectPublicArtifactIds(publicResult);
      if (publicResult?.outcome === "no_change" && publicDescriptors.length === 0 && publicArtifactIds.size === 0 && reservations.length > 0) {
        if (reservations.some((reservation) => reservation.kind !== "file")) {
          throw new Error("No-change output cleanup accepts only exact file reservations.");
        }
        for (const reservation of reservations) {
          this.abortPrivateArtifactReservation({
            artifactId: reservation.artifactId,
            operationId,
            accountFingerprint,
            identity: reservation.identity,
          });
        }
        return Object.freeze([]);
      }
      const reservedIds = new Set(reservations.map(({artifactId}) => artifactId));
      for (const descriptor of publicDescriptors) {
        if (reservedIds.has(descriptor.artifactId)) continue;
        const referenced = state.artifacts[descriptor.artifactId];
        if (!referenced || referenced.accountFingerprint !== accountFingerprint || referenced.availableUntilMs <= now()
          || referenced.sizeBytes !== descriptor.sizeBytes || referenced.sha256 !== descriptor.sha256) {
          throw new Error(`Prepared-action result exposed an unreserved output artifact: ${descriptor.artifactId}`);
        }
        if (referenced.kind === "directory") assertRecordDirectory(referenced);
        const referencedDescriptor = assertRecordFile(referenced);
        try {
          if (sha256Descriptor(referencedDescriptor, referenced.sizeBytes) !== descriptor.sha256
            || !sameIdentity(fs.fstatSync(referencedDescriptor), referenced)) {
            throw new Error(`Prepared-action result referenced stale artifact bytes: ${descriptor.artifactId}`);
          }
        } finally {
          fs.closeSync(referencedDescriptor);
        }
      }
      const candidates = [];
      const directoryCandidates = [];
      const adoptedCandidates = [];
      const existingPublications = [];
      let committed = false;
      try {
        for (const reservation of reservations) {
          const matches = publicDescriptors.filter(({artifactId}) => artifactId === reservation.artifactId);
          const record = state.reservations[reservation.artifactId];
          if (!record || record.kind !== reservation.kind || record.purpose !== "output"
            || record.operationId !== operationId || record.accountFingerprint !== accountFingerprint
            || record.filePath !== reservation.absolutePath) {
            throw new Error("Prepared-action output reservation custody changed.");
          }
          if (record.kind === "directory") {
            if (!publicArtifactIds.has(reservation.artifactId) || matches.length > 1) {
              throw new Error(`Prepared-action directory output artifact binding is ambiguous: ${reservation.artifactId}`);
            }
            assertCanonicalPrivateDirectory(path.dirname(record.filePath), {label: "Managed render operation directory"});
            const snapshot = privateDirectorySnapshot(record.filePath, record);
            if (snapshot.totalBytes < 1) throw new Error("Prepared-action directory output artifact is empty.");
            const bundlePath = path.join(
              path.dirname(record.filePath),
              `${reservation.artifactId}.directory-output-${crypto.randomUUID()}.cadir`,
            );
            const bundle = materializeDirectoryBundle(record.filePath, snapshot, bundlePath);
            const after = privateDirectorySnapshot(record.filePath, record);
            if (after.treeDigest !== snapshot.treeDigest || after.totalBytes !== snapshot.totalBytes
              || JSON.stringify(after.directories) !== JSON.stringify(snapshot.directories)
              || JSON.stringify(after.directoryEntries) !== JSON.stringify(snapshot.directoryEntries)
              || JSON.stringify(after.entries) !== JSON.stringify(snapshot.entries)) {
              fs.unlinkSync(bundlePath);
              throw new Error("Prepared-action directory output changed during publication.");
            }
            const exact = matches[0];
            if (exact && (exact.sizeBytes !== bundle.sizeBytes || exact.sha256 !== null && exact.sha256 !== bundle.sha256)) {
              fs.unlinkSync(bundlePath);
              throw new Error("Prepared-action directory output did not match its verified bundle descriptor.");
            }
            directoryCandidates.push({reservation, record, snapshot, bundlePath, bundle});
            continue;
          }
          if (!publicArtifactIds.has(reservation.artifactId) || matches.length > 1) {
            throw new Error(`Prepared-action output artifact binding is ambiguous: ${reservation.artifactId}`);
          }
          const exact = matches[0];
          assertCanonicalPrivateDirectory(path.dirname(record.filePath), {label: "Managed render operation directory"});
          const descriptor = fs.openSync(record.filePath, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
          const stat = fs.fstatSync(descriptor);
          const pathStat = fs.lstatSync(record.filePath);
          const expectedSize = exact?.sizeBytes ?? stat.size;
          if (!stat.isFile() || pathStat.isSymbolicLink() || pathStat.dev !== stat.dev || pathStat.ino !== stat.ino
            || stat.dev !== record.dev || stat.ino !== record.ino || stat.size !== expectedSize) {
            fs.closeSync(descriptor);
            throw new Error("Prepared-action output identity does not match its verified result.");
          }
          candidates.push({
            reservation,
            exact: {...(exact ?? {}), sizeBytes: expectedSize, sha256: exact?.sha256 ?? null},
            record,
            descriptor,
            stat,
          });
        }
        const operationDir = path.join(root, operationId);
        for (const artifactId of publicArtifactIds) {
          if (reservedIds.has(artifactId)) continue;
          const existing = state.artifacts[artifactId];
          if (existing) {
            if (existing.accountFingerprint !== accountFingerprint) {
              throw new Error(`Adopted managed artifact ownership collided: ${artifactId}`);
            }
            if (existing.kind === "directory") assertRecordDirectory(existing);
            const descriptor = assertRecordFile(existing);
            try {
              if (sha256Descriptor(descriptor, existing.sizeBytes) !== existing.sha256
                || !sameIdentity(fs.fstatSync(descriptor), existing)) {
                throw new Error(`Adopted managed artifact changed before replay publication: ${artifactId}`);
              }
            } finally {
              fs.closeSync(descriptor);
            }
            if (!publicDescriptorIds.has(artifactId)) {
              existingPublications.push({
                artifact: existing,
                availableUntil: new Date(existing.availableUntilMs).toISOString(),
              });
            }
            continue;
          }
          const privateReservation = state.reservations[artifactId];
          let filePath;
          if (privateReservation) {
            if (privateReservation.kind !== "file" || privateReservation.purpose !== "private"
              || privateReservation.operationId !== operationId
              || privateReservation.accountFingerprint !== accountFingerprint) {
              throw new Error(`Private output artifact reservation ownership changed: ${artifactId}`);
            }
            filePath = privateReservation.filePath;
            assertCanonicalPrivateDirectory(path.dirname(filePath), {label: "Managed artifact operation directory"});
          } else {
            const artifactDir = path.join(operationDir, artifactId);
            assertCanonicalPrivateDirectory(artifactDir, {label: "Adopted managed artifact directory"});
            const names = fs.readdirSync(artifactDir);
            if (names.length !== 1) throw new Error(`Adopted managed artifact is ambiguous: ${artifactId}`);
            filePath = path.join(artifactDir, names[0]);
          }
          const pathStat = fs.lstatSync(filePath);
          const descriptor = fs.openSync(filePath, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
          const stat = fs.fstatSync(descriptor);
          if (!stat.isFile() || pathStat.isSymbolicLink() || pathStat.dev !== stat.dev || pathStat.ino !== stat.ino
            || stat.size < 1 || pathStat.size !== stat.size
            || privateReservation && (stat.dev !== privateReservation.dev || stat.ino !== privateReservation.ino)) {
            fs.closeSync(descriptor);
            throw new Error(`Adopted managed artifact identity is invalid: ${artifactId}`);
          }
          adoptedCandidates.push({artifactId, filePath, descriptor, stat});
        }
        for (const candidate of candidates) {
          const {descriptor, exact, record, stat} = candidate;
          const digest = sha256Descriptor(descriptor, exact.sizeBytes);
          const after = fs.fstatSync(descriptor);
          const afterPath = fs.lstatSync(record.filePath);
          if ((exact.sha256 !== null && digest !== exact.sha256) || !sameIdentity(after, {
            dev: stat.dev, ino: stat.ino, sizeBytes: stat.size, mtimeMs: stat.mtimeMs, ctimeMs: stat.ctimeMs,
          }) || afterPath.isSymbolicLink() || afterPath.dev !== stat.dev || afterPath.ino !== stat.ino
            || afterPath.size !== stat.size || afterPath.mtimeMs !== stat.mtimeMs || afterPath.ctimeMs !== stat.ctimeMs) {
            throw new Error("Prepared-action output bytes do not match their verified digest and identity.");
          }
          fs.fsyncSync(descriptor);
          candidate.sha256 = digest;
        }
        for (const candidate of adoptedCandidates) {
          candidate.sha256 = sha256Descriptor(candidate.descriptor, candidate.stat.size);
          const after = fs.fstatSync(candidate.descriptor);
          const afterPath = fs.lstatSync(candidate.filePath);
          if (!sameIdentity(after, {
            dev: candidate.stat.dev, ino: candidate.stat.ino, sizeBytes: candidate.stat.size,
            mtimeMs: candidate.stat.mtimeMs, ctimeMs: candidate.stat.ctimeMs,
          }) || afterPath.isSymbolicLink() || afterPath.dev !== candidate.stat.dev || afterPath.ino !== candidate.stat.ino
            || afterPath.size !== candidate.stat.size || afterPath.mtimeMs !== candidate.stat.mtimeMs
            || afterPath.ctimeMs !== candidate.stat.ctimeMs) {
            throw new Error(`Adopted managed artifact changed during publication: ${candidate.artifactId}`);
          }
          fs.fsyncSync(candidate.descriptor);
        }
        const createdAtMs = now();
        const publications = [...existingPublications, ...candidates.map(({reservation, exact, record, stat, sha256}) => {
          const artifact = validateRecord({
            artifactId: reservation.artifactId, operationId, accountFingerprint, filePath: record.filePath,
            sizeBytes: exact.sizeBytes, sha256: exact.sha256 ?? sha256,
            dev: stat.dev, ino: stat.ino, mtimeMs: stat.mtimeMs, ctimeMs: stat.ctimeMs,
            resultExpiresAtMs: createdAtMs + resultRetentionMs,
            availableUntilMs: createdAtMs + artifactRetentionMs,
          }, reservation.artifactId, root);
          return {artifact, availableUntil: new Date(artifact.availableUntilMs).toISOString()};
        }), ...directoryCandidates.map(({reservation, record, snapshot, bundlePath, bundle}) => {
          const artifact = validateRecord({
            artifactId: reservation.artifactId, operationId, accountFingerprint,
            kind: "directory", filePath: bundlePath, directoryPath: record.filePath,
            sizeBytes: bundle.sizeBytes, sha256: bundle.sha256,
            dev: bundle.stat.dev, ino: bundle.stat.ino, mtimeMs: bundle.stat.mtimeMs, ctimeMs: bundle.stat.ctimeMs,
            treeDigest: snapshot.treeDigest, totalBytes: snapshot.totalBytes,
            directoryIdentity: {
              dev: record.dev, ino: record.ino,
              mtimeMs: snapshot.identity.mtimeMs, ctimeMs: snapshot.identity.ctimeMs,
            },
            directories: snapshot.directories, directoryEntries: snapshot.directoryEntries, entries: snapshot.entries,
            resultExpiresAtMs: createdAtMs + resultRetentionMs,
            availableUntilMs: createdAtMs + artifactRetentionMs,
          }, reservation.artifactId, root);
          return {artifact, availableUntil: new Date(artifact.availableUntilMs).toISOString()};
        })];
        for (const {artifactId, filePath, stat, sha256} of adoptedCandidates) {
          const artifact = validateRecord({
            artifactId, operationId, accountFingerprint, filePath,
            sizeBytes: stat.size, sha256,
            dev: stat.dev, ino: stat.ino, mtimeMs: stat.mtimeMs, ctimeMs: stat.ctimeMs,
            resultExpiresAtMs: createdAtMs + resultRetentionMs,
            availableUntilMs: createdAtMs + artifactRetentionMs,
          }, artifactId, root);
          publications.push({artifact, availableUntil: new Date(artifact.availableUntilMs).toISOString()});
        }
        if (publications.length) {
          const nextState = {
            ...state,
            artifacts: {...state.artifacts},
            reservations: {...state.reservations},
          };
          for (const {artifact} of publications) {
            nextState.artifacts[artifact.artifactId] = artifact;
            delete nextState.reservations[artifact.artifactId];
          }
          writePrivateJsonDurableAtomic(statePath, nextState);
          state = nextState;
        }
        committed = true;
        return Object.freeze(publications.map(({artifact, availableUntil}) => Object.freeze({artifactId: artifact.artifactId, availableUntil})));
      } finally {
        for (const candidate of candidates) fs.closeSync(candidate.descriptor);
        for (const candidate of adoptedCandidates) fs.closeSync(candidate.descriptor);
        if (!committed) {
          for (const candidate of directoryCandidates) {
            try { fs.unlinkSync(candidate.bundlePath); } catch { /* Preserve the publication failure. */ }
          }
        }
      }
    },
    capturePrivateManagedArtifact({artifactId, accountFingerprint}) {
      cleanup();
      sdkArtifactIdSchema.parse(artifactId);
      const record = state.artifacts[artifactId];
      const reservation = state.reservations[artifactId];
      if (!record && reservation?.kind === "file" && reservation.purpose === "private"
        && reservation.accountFingerprint === accountFingerprint && reservation.availableUntilMs > now()) {
        const descriptor = fs.openSync(reservation.filePath, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW ?? 0));
        try {
          const stat = fs.fstatSync(descriptor);
          const pathStat = fs.lstatSync(reservation.filePath);
          if (!stat.isFile() || pathStat.isSymbolicLink() || stat.dev !== reservation.dev || stat.ino !== reservation.ino
            || pathStat.dev !== stat.dev || pathStat.ino !== stat.ino) {
            throw new Error("The managed private artifact reservation identity changed.");
          }
          const digest = sha256Descriptor(descriptor, stat.size);
          const after = fs.fstatSync(descriptor);
          if (!sameIdentity(after, {dev: stat.dev, ino: stat.ino, sizeBytes: stat.size, mtimeMs: stat.mtimeMs, ctimeMs: stat.ctimeMs})) {
            throw new Error("The managed private artifact changed during capture.");
          }
          return Object.freeze({
            artifactId, absolutePath: reservation.filePath, sizeBytes: stat.size, sha256: digest,
            identity: Object.freeze({device: stat.dev, inode: stat.ino, mtimeMs: stat.mtimeMs, ctimeMs: stat.ctimeMs}),
          });
        } finally {
          fs.closeSync(descriptor);
        }
      }
      if (!record || record.accountFingerprint !== accountFingerprint || record.availableUntilMs <= now()) {
        const error = new Error("The managed artifact is unavailable.");
        error.code = "TARGET_NOT_FOUND";
        throw error;
      }
      if (record.kind !== "file") {
        const error = new Error("The managed artifact is not a file artifact.");
        error.code = "TARGET_NOT_FOUND";
        throw error;
      }
      const descriptor = assertRecordFile(record);
      try {
        const digest = sha256Descriptor(descriptor, record.sizeBytes);
        const after = fs.fstatSync(descriptor);
        if (digest !== record.sha256 || !sameIdentity(after, record)) throw new Error("The managed artifact changed during private capture.");
        return Object.freeze({
          artifactId,
          absolutePath: record.filePath,
          sizeBytes: record.sizeBytes,
          sha256: record.sha256,
          identity: Object.freeze({device: record.dev, inode: record.ino, mtimeMs: record.mtimeMs, ctimeMs: record.ctimeMs}),
        });
      } finally {
        fs.closeSync(descriptor);
      }
    },
    capturePrivateManagedDirectory({artifactId, accountFingerprint, singleDirectorySuffix = null, singleDirectoryName = null}) {
      cleanup();
      sdkArtifactIdSchema.parse(artifactId);
      if (singleDirectorySuffix !== null && (!/^\.[A-Za-z0-9]{1,16}$/.test(singleDirectorySuffix))) {
        throw new TypeError("Managed directory artifact suffix selector is invalid.");
      }
      if (singleDirectoryName !== null && (!/^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$/.test(singleDirectoryName))) {
        throw new TypeError("Managed directory artifact name selector is invalid.");
      }
      if (singleDirectorySuffix !== null && singleDirectoryName !== null) {
        throw new TypeError("Managed directory artifact selectors are mutually exclusive.");
      }
      const reservation = state.reservations[artifactId];
      const published = state.artifacts[artifactId];
      const source = reservation?.kind === "directory" ? reservation : published?.kind === "directory" ? published : null;
      if (!source || source.accountFingerprint !== accountFingerprint || source.availableUntilMs <= now()) {
        const error = new Error("The managed directory artifact is unavailable.");
        error.code = "TARGET_NOT_FOUND";
        throw error;
      }
      if (source === published) assertRecordDirectory(published);
      const sourcePath = source === published ? published.directoryPath : reservation.filePath;
      const sourceIdentity = source === published ? published.directoryIdentity : reservation;
      assertCanonicalPrivateDirectory(path.dirname(sourcePath), {label: "Managed render operation directory"});
      const reservationBefore = fs.lstatSync(sourcePath);
      if (!sameDirectoryIdentity(reservationBefore, sourceIdentity)) throw new Error("The managed directory artifact identity changed.");
      let capturedPath = sourcePath;
      if (singleDirectorySuffix !== null || singleDirectoryName !== null) {
        const matches = fs.readdirSync(sourcePath, {withFileTypes: true})
          .filter((entry) => entry.isDirectory() && !entry.isSymbolicLink()
            && (singleDirectoryName !== null ? entry.name === singleDirectoryName : entry.name.endsWith(singleDirectorySuffix)));
        if (matches.length !== 1) throw new Error("The managed directory artifact has no exact selected child.");
        capturedPath = path.join(sourcePath, matches[0].name);
      }
      const capturedStat = fs.lstatSync(capturedPath);
      const capturedIdentity = {dev: capturedStat.dev, ino: capturedStat.ino};
      const first = privateDirectorySnapshot(capturedPath, capturedIdentity);
      const second = privateDirectorySnapshot(capturedPath, capturedIdentity);
      const reservationAfter = fs.lstatSync(sourcePath);
      if (first.treeDigest !== second.treeDigest || first.totalBytes !== second.totalBytes
        || JSON.stringify(first.identity) !== JSON.stringify(second.identity)
        || JSON.stringify(first.directories) !== JSON.stringify(second.directories)
        || JSON.stringify(first.directoryEntries) !== JSON.stringify(second.directoryEntries)
        || JSON.stringify(first.entries) !== JSON.stringify(second.entries)
        || !sameDirectoryIdentity(reservationAfter, reservationBefore)
        || reservationAfter.mtimeMs !== reservationBefore.mtimeMs || reservationAfter.ctimeMs !== reservationBefore.ctimeMs) {
        throw new Error("The managed directory changed during private capture.");
      }
      if (source === published) assertRecordDirectory(published);
      return Object.freeze({
        artifactId, absolutePath: capturedPath,
        treeDigest: first.treeDigest, totalBytes: first.totalBytes,
        directories: first.directories, directoryEntries: first.directoryEntries, entries: first.entries,
        identity: Object.freeze(first.identity),
      });
    },
    revalidatePrivateManagedDirectory({artifactId, accountFingerprint, treeDigest}) {
      if (!SHA256_PATTERN.test(treeDigest ?? "")) throw new TypeError("Managed directory tree digest is invalid.");
      const captured = this.capturePrivateManagedDirectory({artifactId, accountFingerprint});
      if (captured.treeDigest !== treeDigest) throw new Error("The managed directory hierarchy changed before execution.");
      return captured;
    },
    reservePrivateManagedArtifact({artifactId, operationId, accountFingerprint, extension}) {
      return reservePrivateFile({artifactId, operationId, accountFingerprint, extension}, "private");
    },
    reservePrivateOutputArtifact({artifactId, operationId, accountFingerprint, extension}) {
      return reservePrivateFile({artifactId, operationId, accountFingerprint, extension}, "output");
    },
    reservePrivateManagedDirectory({artifactId, operationId, accountFingerprint}) {
      return reservePrivateDirectory({artifactId, operationId, accountFingerprint}, "private");
    },
    reservePrivateOutputDirectory({artifactId, operationId, accountFingerprint}) {
      return reservePrivateDirectory({artifactId, operationId, accountFingerprint}, "output");
    },
    register({ artifactId, operationId, accountFingerprint, filePath, sizeBytes, sha256 }) {
      sdkArtifactIdSchema.parse(artifactId);
      sdkOperationIdSchema.parse(operationId);
      if (!ACCOUNT_FINGERPRINT_PATTERN.test(accountFingerprint ?? "") || !SHA256_PATTERN.test(sha256 ?? "")) {
        throw new TypeError("SDK artifact ownership or digest is invalid.");
      }
      const absolute = path.resolve(filePath);
      const relative = path.relative(root, absolute);
      if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("SDK artifact escaped its managed root.");
      const noFollow = Number.isInteger(fs.constants.O_NOFOLLOW) ? fs.constants.O_NOFOLLOW : 0;
      const descriptor = fs.openSync(absolute, fs.constants.O_RDONLY | noFollow);
      try {
        const stat = fs.fstatSync(descriptor);
        const pathStat = fs.lstatSync(absolute);
        const reservation = state.reservations[artifactId];
        if (reservation?.kind === "directory") throw new Error("SDK file publication cannot consume a directory reservation.");
        if (reservation && (reservation.operationId !== operationId
          || reservation.accountFingerprint !== accountFingerprint
          || reservation.filePath !== absolute
          || reservation.dev !== stat.dev || reservation.ino !== stat.ino)) {
          throw new Error("SDK artifact publication changed its private reservation custody.");
        }
        if (!stat.isFile() || pathStat.isSymbolicLink() || pathStat.dev !== stat.dev || pathStat.ino !== stat.ino || stat.size !== sizeBytes) {
          throw new Error("SDK artifact identity does not match its verified result.");
        }
        const verifiedDigest = sha256Descriptor(descriptor, sizeBytes);
        const after = fs.fstatSync(descriptor);
        const afterPath = fs.lstatSync(absolute);
        if (verifiedDigest !== sha256 || after.dev !== stat.dev || after.ino !== stat.ino || after.size !== stat.size
          || after.mtimeMs !== stat.mtimeMs || after.ctimeMs !== stat.ctimeMs
          || afterPath.isSymbolicLink() || afterPath.dev !== stat.dev || afterPath.ino !== stat.ino || afterPath.size !== stat.size) {
          throw new Error("SDK artifact bytes do not match their verified digest and identity.");
        }
        fs.fsyncSync(descriptor);
        const createdAtMs = now();
        const record = validateRecord({
          artifactId, operationId, accountFingerprint, filePath: absolute, sizeBytes, sha256,
          dev: stat.dev, ino: stat.ino, mtimeMs: stat.mtimeMs, ctimeMs: stat.ctimeMs,
          resultExpiresAtMs: createdAtMs + resultRetentionMs,
          availableUntilMs: createdAtMs + artifactRetentionMs,
        }, artifactId, root);
        state.artifacts[artifactId] = record;
        delete state.reservations[artifactId];
        persist();
        return { availableUntil: new Date(record.availableUntilMs).toISOString() };
      } finally {
        fs.closeSync(descriptor);
      }
    },
    read({ artifactId, accountFingerprint, offset, length }) {
      cleanup();
      sdkArtifactIdSchema.parse(artifactId);
      if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isInteger(length) || length < 1 || length > MAX_CHUNK_BYTES) {
        throw new TypeError("SDK artifact chunk coordinates are invalid.");
      }
      const record = state.artifacts[artifactId];
      if (!record || record.accountFingerprint !== accountFingerprint || record.availableUntilMs <= now()) {
        const error = new Error("The managed artifact is unavailable.");
        error.code = "TARGET_NOT_FOUND";
        throw error;
      }
      if (offset > record.sizeBytes) {
        const error = new Error("The managed artifact offset is outside the artifact.");
        error.code = "INVALID_REQUEST";
        throw error;
      }
      const descriptor = assertRecordFile(record);
      try {
        const count = Math.min(length, record.sizeBytes - offset);
        const bytes = Buffer.alloc(count);
        const bytesRead = count ? fs.readSync(descriptor, bytes, 0, count, offset) : 0;
        const after = fs.fstatSync(descriptor);
        if (bytesRead !== count || !sameIdentity(after, record)) {
          const error = new Error("The managed artifact changed while it was being read.");
          error.code = "TARGET_NOT_FOUND";
          throw error;
        }
        return sdkArtifactContentChunkSchema.parse({
          artifactId,
          offset,
          totalSize: record.sizeBytes,
          bytesBase64: bytes.subarray(0, bytesRead).toString("base64"),
          eof: offset + bytesRead === record.sizeBytes,
          sha256: record.sha256,
          availableUntil: new Date(record.availableUntilMs).toISOString(),
        });
      } finally {
        fs.closeSync(descriptor);
      }
    },
    cleanup,
    stop() { clearInterval(timer); },
  });
}
