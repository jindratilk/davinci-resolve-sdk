import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
  sdkOperationResultCollectionReferenceSchema,
  sdkOperationSnapshotSchema,
  sdkPublicActionIdSchema,
} from "../contracts/generated/sdk-operations.js";
import {
  sdkIdempotencyKeySchema,
  sdkOperationIdSchema,
  sdkSessionIdSchema,
} from "../contracts/generated/sdk-identities.js";
import {
  PRIVATE_DIR_MODE,
  PRIVATE_FILE_MODE,
  assertCanonicalPrivateDirectory,
  ensureCanonicalPrivateDirectory,
  writePrivateJsonDurableAtomic,
} from "../services/private-storage.js";
import {
  canonicalSdkOperationInput,
  sdkOperationInputDigest,
} from "../services/sdk-operation-input.js";
import {
  SDK_OPERATION_RESULT_COLLECTION_MAX_BYTES,
  SDK_OPERATION_RESULT_COLLECTION_MAX_ITEMS,
  sdkOperationResultCollectionDigest,
} from "../services/sdk-operation-result-collections.js";
import {
  CUTAGENT_PREPARED_ACTION_PROTOCOL_VERSION,
  sdkPreparedActionTerminalSchema,
  sdkPrepareActionRequestSchema,
} from "../contracts/generated/sdk-prepared-action.js";

import { readLegacySdkPublicFailure } from "../services/sdk-legacy-public-failure.js";

const STATE_VERSION = 1;
const PREPARED_TERMINAL_RESERVE_BYTES = 8 * 1024 * 1024;
const INSTALLATION_AUTHORITY_PATTERN = /^sdk_installation_[A-Za-z0-9._~-]+$/;
const ACCOUNT_FINGERPRINT_PATTERN = /^[A-Za-z0-9_-]{20,128}$/;
const DIGEST_PATTERN = /^sha256:[a-f0-9]{64}$/;
const POSIX_MODE_MASK = 0o777;
const TERMINAL_STATUSES = new Set([
  "succeeded", "failed", "cancelled", "partially_applied", "verification_failed", "recovery_failed",
]);
const STATUS_TRANSITIONS = Object.freeze({
  queued: new Set(["queued", "running", "waiting", "cancellation_requested", ...TERMINAL_STATUSES]),
  running: new Set(["running", "waiting", "cancellation_requested", ...TERMINAL_STATUSES]),
  waiting: new Set(["waiting", "running", "cancellation_requested", ...TERMINAL_STATUSES]),
  cancellation_requested: new Set(["cancellation_requested", "running", "waiting", ...TERMINAL_STATUSES]),
});
const PROCESS_REPO_OWNERS = new Map();
const OWNER_LOCK_NAME = ".sdk-operation-authority-owner-v1";
const OWNER_RECORD_NAME = "owner.json";

function installationAuthority() {
  return `sdk_installation_${crypto.randomUUID()}`;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseStoredPreparedActionRequest(value) {
  if (isPlainObject(value) && value.protocolVersion === 1
    && CUTAGENT_PREPARED_ACTION_PROTOCOL_VERSION !== 1) {
    return sdkPrepareActionRequestSchema.parse({
      ...value,
      protocolVersion: CUTAGENT_PREPARED_ACTION_PROTOCOL_VERSION,
    });
  }
  return sdkPrepareActionRequestSchema.parse(value);
}

function resultPageReferences(value, output = new Map()) {
  if (Array.isArray(value)) {
    value.forEach((entry) => resultPageReferences(entry, output));
    return output;
  }
  if (!isPlainObject(value)) return output;
  if (Object.hasOwn(value, "resultPage")) {
    const reference = sdkOperationResultCollectionReferenceSchema.parse(value.resultPage);
    if (output.has(reference.collectionId)) throw new Error("SDK result page reference is duplicated.");
    output.set(reference.collectionId, reference);
  }
  Object.values(value).forEach((entry) => resultPageReferences(entry, output));
  return output;
}

function validateResultCollections(record, snapshot, operationId) {
  const references = snapshot.result === undefined
    ? new Map()
    : resultPageReferences(snapshot.result.value);
  const collections = record.private.resultCollections;
  if (collections === undefined) {
    if (references.size > 0) throw new Error(`SDK operation result pages are missing durable truth: ${operationId}`);
    return;
  }
  if (!isPlainObject(collections) || Object.keys(collections).length !== references.size || references.size > 8) {
    throw new Error(`SDK operation result collections are malformed: ${operationId}`);
  }
  for (const [collectionId, collection] of Object.entries(collections)) {
    const reference = references.get(collectionId);
    if (!reference || !isPlainObject(collection) || collection.kind !== reference.kind
      || collection.digest !== reference.digest || !Array.isArray(collection.entries)
      || collection.entries.length !== reference.totalItems
      || collection.entries.length > SDK_OPERATION_RESULT_COLLECTION_MAX_ITEMS
      || Buffer.byteLength(JSON.stringify(collection.entries), "utf8") > SDK_OPERATION_RESULT_COLLECTION_MAX_BYTES
      || sdkOperationResultCollectionDigest(collection.kind, collection.entries) !== collection.digest) {
      throw new Error(`SDK operation result collection does not match its public reference: ${operationId}/${collectionId}`);
    }
    const keys = new Set();
    collection.entries.forEach((entry, index) => {
      if (!isPlainObject(entry) || !("value" in entry)) throw new Error(`SDK operation result collection entry is malformed: ${operationId}/${collectionId}`);
      if (collection.kind === "array") {
        if (entry.index !== index || Object.keys(entry).some((key) => !["index", "value"].includes(key))) {
          throw new Error(`SDK operation array result collection is malformed: ${operationId}/${collectionId}`);
        }
      } else if (typeof entry.key !== "string" || !entry.key || entry.key.length > 160
        || keys.has(entry.key) || Object.keys(entry).some((key) => !["key", "value"].includes(key))) {
        throw new Error(`SDK operation identity-map result collection is malformed: ${operationId}/${collectionId}`);
      } else {
        keys.add(entry.key);
      }
      canonicalSdkOperationInput(entry.value);
    });
  }
}

function validatePrivateRecord(record, operationId, authority) {
  if (!isPlainObject(record) || !isPlainObject(record.public) || !isPlainObject(record.private)) {
    throw new Error(`SDK operation record is malformed: ${operationId}`);
  }
  const snapshot = sdkOperationSnapshotSchema.parse(record.public);
  if (snapshot.operationId !== operationId) throw new Error(`SDK operation key does not match its record: ${operationId}`);
  if (!ACCOUNT_FINGERPRINT_PATTERN.test(record.private.accountFingerprint ?? "")) {
    throw new Error(`SDK operation account ownership is malformed: ${operationId}`);
  }
  if (record.private.installationAuthority !== authority) {
    throw new Error(`SDK operation installation ownership is malformed: ${operationId}`);
  }
  if (record.private.sdkSessionId !== undefined
    && !sdkSessionIdSchema.safeParse(record.private.sdkSessionId).success) {
    throw new Error(`SDK operation session identity is malformed: ${operationId}`);
  }
  if (!DIGEST_PATTERN.test(record.private.normalizedInputDigest ?? "")) {
    throw new Error(`SDK operation normalized input digest is malformed: ${operationId}`);
  }
  if (record.private.workflowRetentionExpiresAt !== undefined
    && !Number.isFinite(Date.parse(record.private.workflowRetentionExpiresAt))) {
    throw new Error(`SDK operation workflow retention is malformed: ${operationId}`);
  }
  if (!("normalizedInput" in record.private)) {
    throw new Error(`SDK operation normalized input is missing: ${operationId}`);
  }
  if (record.private.preparedActionTerminal !== undefined) {
    const terminal = sdkPreparedActionTerminalSchema.parse(record.private.preparedActionTerminal);
    if (terminal.operationId !== operationId || terminal.actionId !== snapshot.actionId
      || terminal.executionId !== snapshot.executionId || !TERMINAL_STATUSES.has(snapshot.status)) {
      throw new Error(`SDK prepared-action terminal does not match its durable operation: ${operationId}`);
    }
  }
  let normalizedPreparedActionRequest;
  if (record.private.preparedActionRequest !== undefined) {
    const request = parseStoredPreparedActionRequest(record.private.preparedActionRequest);
    normalizedPreparedActionRequest = request;
    if (request.operationId !== operationId || request.executionId !== snapshot.executionId
      || request.requestId !== snapshot.requestId || request.actionId !== snapshot.actionId) {
      throw new Error(`SDK prepared-action request does not match its durable operation: ${operationId}`);
    }
  }
  let canonicalInput;
  try {
    canonicalInput = canonicalSdkOperationInput(record.private.normalizedInput);
  } catch {
    throw new Error(`SDK operation normalized input is malformed: ${operationId}`);
  }
  if (sdkOperationInputDigest(canonicalInput) !== record.private.normalizedInputDigest) {
    throw new Error(`SDK operation normalized input digest does not match its record: ${operationId}`);
  }
  validateResultCollections(record, snapshot, operationId);
  const privateRecord = structuredClone(record.private);
  if (normalizedPreparedActionRequest) {
    privateRecord.preparedActionRequest = normalizedPreparedActionRequest;
  }
  return { public: snapshot, private: privateRecord };
}

function validateReservation(reservation, key, authority) {
  if (!isPlainObject(reservation)
    || !ACCOUNT_FINGERPRINT_PATTERN.test(reservation.accountFingerprint ?? "")
    || reservation.installationAuthority !== authority
    || !sdkIdempotencyKeySchema.safeParse(reservation.key).success
    || !sdkPublicActionIdSchema.safeParse(reservation.actionId).success
    || reservation.actionContractVersion !== 1
    || !DIGEST_PATTERN.test(reservation.normalizedInputDigest ?? "")
    || !sdkOperationIdSchema.safeParse(reservation.operationId).success
    || !Number.isFinite(reservation.resultExpiresAt)
    || !Number.isFinite(reservation.tombstoneExpiresAt)
    || reservation.tombstoneExpiresAt <= reservation.resultExpiresAt
    || reservationStorageKey(reservation.accountFingerprint, reservation.key) !== key) {
    throw new Error(`SDK idempotency reservation is malformed: ${key}`);
  }
  return structuredClone(reservation);
}

function assertReservationMatchesOperation(reservation, operation, storageKey) {
  if (!operation) return;
  if (reservation.operationId !== operation.public.operationId
    || reservation.accountFingerprint !== operation.private.accountFingerprint
    || reservation.installationAuthority !== operation.private.installationAuthority
    || reservation.actionId !== operation.public.actionId
    || reservation.actionContractVersion !== operation.public.actionContractVersion
    || reservation.normalizedInputDigest !== operation.private.normalizedInputDigest
    || operation.public.idempotency?.key !== reservation.key) {
    throw new Error(`SDK idempotency reservation does not match its retained operation: ${storageKey}`);
  }
}

function assertEveryIdempotentOperationHasReservation(operations, idempotency) {
  for (const [operationId, operation] of Object.entries(operations)) {
    const idempotencyKey = operation.public.idempotency?.key;
    if (!idempotencyKey) continue;
    const storageKey = reservationStorageKey(operation.private.accountFingerprint, idempotencyKey);
    const reservation = idempotency[storageKey];
    if (!reservation) {
      throw new Error(`Retained SDK operation is missing its idempotency reservation: ${operationId}`);
    }
    assertReservationMatchesOperation(reservation, operation, storageKey);
  }
}

function privateIdentity(stat) {
  return Object.freeze({
    dev: stat.dev,
    ino: stat.ino,
    uid: stat.uid,
    gid: stat.gid,
    mode: stat.mode & POSIX_MODE_MASK,
  });
}

function assertPrivateOwnershipAndMode(stat, expected, label) {
  if (process.platform === "win32") return;
  if (stat.uid !== expected.uid || stat.gid !== expected.gid || (stat.mode & POSIX_MODE_MASK) !== expected.mode) {
    throw new Error(`${label} ownership or private mode changed after initialization.`);
  }
}

function processIsAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error?.code === "ESRCH") return false;
    if (error?.code === "EPERM") return true;
    throw error;
  }
}

function acquireCrossProcessOwner(canonicalStorageDir, storageIdentity) {
  const lockPath = path.join(canonicalStorageDir, OWNER_LOCK_NAME);
  const token = crypto.randomUUID();
  const claimPath = path.join(canonicalStorageDir, `.${OWNER_LOCK_NAME}.claim-${process.pid}-${token}`);
  const ownerRecord = {version: 1, pid: process.pid, token};
  let claimed = false;

  fs.mkdirSync(claimPath, {mode: PRIVATE_DIR_MODE});
  try {
    const ownerPath = path.join(claimPath, OWNER_RECORD_NAME);
    const fd = fs.openSync(ownerPath, "wx", PRIVATE_FILE_MODE);
    try {
      fs.writeFileSync(fd, `${JSON.stringify(ownerRecord)}\n`, "utf8");
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }

    for (;;) {
      try {
        fs.renameSync(claimPath, lockPath);
        claimed = true;
        break;
      } catch (error) {
        const collision = ["EEXIST", "ENOTEMPTY", "EPERM"].includes(error?.code)
          && fs.existsSync(lockPath);
        if (!collision) throw error;
      }

      const lockStat = fs.lstatSync(lockPath);
      if (!lockStat.isDirectory() || lockStat.isSymbolicLink()) {
        throw new Error("SDK operation storage owner lock is not a private directory.");
      }
      assertPrivateOwnershipAndMode(lockStat, {
        ...storageIdentity,
        mode: PRIVATE_DIR_MODE,
      }, "SDK operation storage owner lock");
      const incumbentPath = path.join(lockPath, OWNER_RECORD_NAME);
      const incumbentStat = fs.lstatSync(incumbentPath);
      if (!incumbentStat.isFile() || incumbentStat.isSymbolicLink() || incumbentStat.size > 1024) {
        throw new Error("SDK operation storage owner record is invalid.");
      }
      assertPrivateOwnershipAndMode(incumbentStat, {
        ...storageIdentity,
        mode: PRIVATE_FILE_MODE,
      }, "SDK operation storage owner record");
      let incumbent;
      try {
        incumbent = JSON.parse(fs.readFileSync(incumbentPath, "utf8"));
      } catch (error) {
        throw new Error("SDK operation storage owner record is unreadable.", {cause: error});
      }
      if (!isPlainObject(incumbent) || incumbent.version !== 1
        || !Number.isSafeInteger(incumbent.pid) || incumbent.pid < 1
        || typeof incumbent.token !== "string" || !/^[a-f0-9-]{36}$/.test(incumbent.token)) {
        throw new Error("SDK operation storage owner record is malformed.");
      }
      if (processIsAlive(incumbent.pid)) {
        throw new Error("SDK operation storage already has a live process owner.");
      }

      const stalePath = path.join(canonicalStorageDir, `.${OWNER_LOCK_NAME}.stale-${incumbent.token}-${crypto.randomUUID()}`);
      try {
        fs.renameSync(lockPath, stalePath);
      } catch (error) {
        if (["ENOENT", "EEXIST", "ENOTEMPTY"].includes(error?.code)) continue;
        throw error;
      }
      const staleStat = fs.lstatSync(stalePath);
      if (staleStat.dev !== lockStat.dev || staleStat.ino !== lockStat.ino) {
        throw new Error("SDK operation stale owner identity changed during reclamation.");
      }
      fs.rmSync(stalePath, {recursive: true, force: false});
    }

    const lockIdentity = privateIdentity(fs.lstatSync(lockPath));
    const claimedOwnerPath = path.join(lockPath, OWNER_RECORD_NAME);
    const ownerIdentity = privateIdentity(fs.lstatSync(claimedOwnerPath));
    const assertLeaseOwnership = () => {
      const current = fs.lstatSync(lockPath);
      if (!current.isDirectory() || current.isSymbolicLink()
        || current.dev !== lockIdentity.dev || current.ino !== lockIdentity.ino) {
        throw new Error("SDK operation storage cross-process ownership was lost.");
      }
      assertPrivateOwnershipAndMode(current, lockIdentity, "SDK operation storage owner lock");
      const currentOwner = fs.lstatSync(claimedOwnerPath);
      if (!currentOwner.isFile() || currentOwner.isSymbolicLink() || currentOwner.size > 1024
        || currentOwner.dev !== ownerIdentity.dev || currentOwner.ino !== ownerIdentity.ino) {
        throw new Error("SDK operation storage cross-process owner record changed.");
      }
      assertPrivateOwnershipAndMode(currentOwner, ownerIdentity, "SDK operation storage owner record");
      const currentRecord = JSON.parse(fs.readFileSync(claimedOwnerPath, "utf8"));
      if (currentRecord?.version !== 1 || currentRecord.pid !== process.pid || currentRecord.token !== token) {
        throw new Error("SDK operation storage cross-process owner changed.");
      }
    };
    return Object.freeze({
      assertOwnership: assertLeaseOwnership,
      release() {
        assertLeaseOwnership();
        fs.rmSync(lockPath, {recursive: true, force: false});
      },
    });
  } catch (error) {
    fs.rmSync(claimPath, {recursive: true, force: true});
    if (claimed) {
      try {
        const current = JSON.parse(fs.readFileSync(path.join(lockPath, OWNER_RECORD_NAME), "utf8"));
        if (current?.pid === process.pid && current?.token === token) {
          fs.rmSync(lockPath, {recursive: true, force: false});
        }
      } catch {}
    }
    throw error;
  }
}

function captureStateFileIdentity(filePath, directoryIdentity) {
  const stat = fs.lstatSync(filePath);
  if (stat.isSymbolicLink() || !stat.isFile()) {
    throw new Error("SDK operation durable state must be a regular non-symlink file.");
  }
  if (process.platform !== "win32"
    && (stat.uid !== directoryIdentity.uid
      || stat.gid !== directoryIdentity.gid
      || (stat.mode & POSIX_MODE_MASK) !== PRIVATE_FILE_MODE)) {
    throw new Error("SDK operation durable state ownership or private mode is invalid.");
  }
  return privateIdentity(stat);
}

function assertStatusTransition(previous, next) {
  if (!STATUS_TRANSITIONS[previous]?.has(next)) {
    throw new Error(`SDK operation status transition is invalid: ${previous} -> ${next}`);
  }
}

function withoutIntermediateProgress(snapshot) {
  const {
    status: _status,
    sequence: _sequence,
    updatedAt: _updatedAt,
    progress: _progress,
    waitingFor: _waitingFor,
    ...durableTruth
  } = snapshot;
  return durableTruth;
}

function loadState(filePath) {
  if (!fs.existsSync(filePath)) {
    return {
      version: STATE_VERSION,
      installationAuthority: installationAuthority(),
      operations: {},
      idempotency: {},
    };
  }
  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    throw new Error("Durable SDK operation state is unreadable; refusing to discard execution truth.", { cause: error });
  }
  if (!isPlainObject(raw)
    || raw.version !== STATE_VERSION
    || !INSTALLATION_AUTHORITY_PATTERN.test(raw.installationAuthority ?? "")
    || !isPlainObject(raw.operations)
    || !isPlainObject(raw.idempotency)) {
    throw new Error("Durable SDK operation state is incompatible or malformed.");
  }
  const operations = Object.fromEntries(Object.entries(raw.operations).map(([operationId, record]) => [
    operationId,
    validatePrivateRecord(record?.public?.failure ? {
      ...record, public: { ...record.public, failure: readLegacySdkPublicFailure(record.public.failure) },
    } : record, operationId, raw.installationAuthority),
  ]));
  const idempotency = Object.fromEntries(Object.entries(raw.idempotency).map(([key, reservation]) => {
    const validated = validateReservation(reservation, key, raw.installationAuthority);
    assertReservationMatchesOperation(validated, operations[validated.operationId], key);
    return [key, validated];
  }));
  assertEveryIdempotentOperationHasReservation(operations, idempotency);
  return { ...raw, operations, idempotency };
}

function reservationStorageKey(accountFingerprint, key) {
  return crypto.createHash("sha256").update(`${accountFingerprint}\0${key}`, "utf8").digest("hex");
}

/**
 * Dedicated durable SDK operation store. Legacy bridge jobs are intentionally
 * not imported, projected, migrated, or addressed by this repository.
 */
export function createSdkOperationRepo({ storageDir }) {
  if (typeof storageDir !== "string" || !storageDir.trim()) {
    throw new Error("createSdkOperationRepo requires a storageDir.");
  }
  const canonicalStorageDir = ensureCanonicalPrivateDirectory(storageDir, {
    label: "SDK operation storage directory",
  });
  const initialStorageStat = fs.lstatSync(canonicalStorageDir);
  const storageIdentity = privateIdentity(initialStorageStat);
  if (process.platform !== "win32" && storageIdentity.mode !== PRIVATE_DIR_MODE) {
    throw new Error("SDK operation storage directory private mode is invalid.");
  }
  const assertStorageIdentityCurrent = () => {
    assertCanonicalPrivateDirectory(canonicalStorageDir, {
      label: "SDK operation storage directory",
    });
    const current = fs.lstatSync(canonicalStorageDir);
    if (!current.isDirectory()
      || current.isSymbolicLink()
      || current.dev !== storageIdentity.dev
      || current.ino !== storageIdentity.ino) {
      throw new Error("SDK operation storage directory identity changed after initialization.");
    }
    assertPrivateOwnershipAndMode(current, storageIdentity, "SDK operation storage directory");
  };
  const priorOwner = PROCESS_REPO_OWNERS.get(canonicalStorageDir);
  if (priorOwner?.hasActive()) {
    throw new Error("SDK operation storage already has a live process owner.");
  }
  const crossProcessOwner = priorOwner?.crossProcessOwner
    ?? acquireCrossProcessOwner(canonicalStorageDir, storageIdentity);
  const acquiredCrossProcessOwner = !priorOwner;
  const filePath = path.join(canonicalStorageDir, "sdk-operation-authority-v1.json");
  const preparedReservePath = path.join(canonicalStorageDir, "sdk-prepared-terminal-reserve-v1");
  let stateFileIdentity;
  let state;
  try {
    assertStorageIdentityCurrent();
    const stateFileExisted = fs.existsSync(filePath);
    stateFileIdentity = stateFileExisted
      ? captureStateFileIdentity(filePath, storageIdentity)
      : null;
    state = loadState(filePath);
    assertStorageIdentityCurrent();
    if (stateFileIdentity) {
      const current = captureStateFileIdentity(filePath, storageIdentity);
      if (current.dev !== stateFileIdentity.dev || current.ino !== stateFileIdentity.ino) {
        throw new Error("SDK operation durable state file identity changed while loading.");
      }
    } else {
      assertStorageIdentityCurrent();
      if (fs.existsSync(filePath)) {
        throw new Error("SDK operation durable state appeared during initialization.");
      }
      writePrivateJsonDurableAtomic(filePath, state);
      stateFileIdentity = captureStateFileIdentity(filePath, storageIdentity);
    }
  } catch (error) {
    if (acquiredCrossProcessOwner) {
      try { crossProcessOwner.release(); } catch {}
    }
    throw error;
  }

  priorOwner?.revoke();
  const ownerToken = crypto.randomUUID();
  let ownershipReleased = false;
  const processOwner = {
    token: ownerToken,
    crossProcessOwner,
    hasActive() {
      return Object.values(state.operations).some(
        (record) => !TERMINAL_STATUSES.has(record.public.status),
      );
    },
    revoke() { ownershipReleased = true; },
  };
  PROCESS_REPO_OWNERS.set(canonicalStorageDir, processOwner);

  function assertOwnership() {
    if (ownershipReleased
      || PROCESS_REPO_OWNERS.get(canonicalStorageDir)?.token !== ownerToken) {
      throw new Error("SDK operation storage process ownership was lost.");
    }
    assertStorageIdentityCurrent();
    crossProcessOwner.assertOwnership();
    return true;
  }

  function commit(next) {
    assertOwnership();
    assertEveryIdempotentOperationHasReservation(next.operations, next.idempotency);
    assertStorageIdentityCurrent();
    const currentStateFileIdentity = captureStateFileIdentity(filePath, storageIdentity);
    if (!stateFileIdentity
      || currentStateFileIdentity.dev !== stateFileIdentity.dev
      || currentStateFileIdentity.ino !== stateFileIdentity.ino) {
      throw new Error("SDK operation durable state file identity changed after initialization.");
    }
    writePrivateJsonDurableAtomic(filePath, next);
    stateFileIdentity = captureStateFileIdentity(filePath, storageIdentity);
    state = next;
  }

  function operationRetentionExpired(record, at) {
    const workflowRetention = Date.parse(record.private.workflowRetentionExpiresAt ?? "");
    return "retentionExpiresAt" in record.public
      && Date.parse(record.public.retentionExpiresAt) <= at
      && (!Number.isFinite(workflowRetention) || workflowRetention <= at);
  }

  function cleanupState(current, at) {
    let operations = current.operations;
    let idempotency = current.idempotency;
    let changed = false;
    for (const [operationId, record] of Object.entries(operations)) {
      if (operationRetentionExpired(record, at)) {
        if (operations === current.operations) operations = {...operations};
        delete operations[operationId];
        changed = true;
      }
    }
    for (const [key, reservation] of Object.entries(idempotency)) {
      const operation = operations[reservation.operationId];
      if (reservation.tombstoneExpiresAt <= at && !operation) {
        if (idempotency === current.idempotency) idempotency = {...idempotency};
        delete idempotency[key];
        changed = true;
      }
    }
    return changed ? {...current, operations, idempotency} : null;
  }

  function cleanupTarget(operationId, storageKey, at) {
    const record = state.operations[operationId];
    let operations = state.operations;
    let idempotency = state.idempotency;
    let changed = false;
    if (record && operationRetentionExpired(record, at)) {
      operations = {...operations};
      delete operations[operationId];
      changed = true;
    }
    const relatedStorageKey = storageKey ?? (record?.public.idempotency?.key
      ? reservationStorageKey(record.private.accountFingerprint, record.public.idempotency.key)
      : null);
    const reservation = relatedStorageKey ? idempotency[relatedStorageKey] : null;
    if (reservation && reservation.tombstoneExpiresAt <= at && !operations[reservation.operationId]) {
      idempotency = {...idempotency};
      delete idempotency[relatedStorageKey];
      changed = true;
    }
    if (changed) commit({...state, operations, idempotency});
  }

  function readPreparedReserve() {
    if (!fs.existsSync(preparedReservePath)) return null;
    const fd = fs.openSync(preparedReservePath, "r");
    try {
      const buffer = Buffer.alloc(Math.min(PREPARED_TERMINAL_RESERVE_BYTES, 1024 * 1024));
      const count = fs.readSync(fd, buffer, 0, buffer.length, 0);
      const newline = buffer.subarray(0, count).indexOf(10);
      if (newline < 1) throw new Error("Prepared terminal reserve journal is malformed.");
      return JSON.parse(buffer.subarray(0, newline).toString("utf8"));
    } finally { fs.closeSync(fd); }
  }

  function writePreparedReserve(envelope, {exclusive = false} = {}) {
    const header = Buffer.from(`${JSON.stringify(envelope)}\n`, "utf8");
    if (header.length > 1024 * 1024) throw new Error("Prepared terminal emergency journal exceeded its header bound.");
    const fd = fs.openSync(preparedReservePath, exclusive ? "wx" : "r+");
    try {
      fs.writeSync(fd, header, 0, header.length, 0);
      const zeros = Buffer.alloc(64 * 1024);
      let offset = header.length;
      while (offset < PREPARED_TERMINAL_RESERVE_BYTES) {
        const length = Math.min(zeros.length, PREPARED_TERMINAL_RESERVE_BYTES - offset);
        fs.writeSync(fd, zeros, 0, length, offset);
        offset += length;
      }
      fs.ftruncateSync(fd, PREPARED_TERMINAL_RESERVE_BYTES);
      fs.fsyncSync(fd);
    } finally { fs.closeSync(fd); }
  }

  try {
    const startupPreparedJournal = readPreparedReserve();
    if (startupPreparedJournal?.version === 1 && startupPreparedJournal.state === "operation_record") {
      const operationId = startupPreparedJournal.operationId;
      const validated = validatePrivateRecord(startupPreparedJournal.record, operationId, state.installationAuthority);
      if (!state.operations[operationId] || !TERMINAL_STATUSES.has(state.operations[operationId].public.status)) {
        const recovered = structuredClone(state);
        recovered.operations[operationId] = validated;
        commit(recovered);
      }
      fs.unlinkSync(preparedReservePath);
    }
  } catch (error) {
    if (PROCESS_REPO_OWNERS.get(canonicalStorageDir)?.token === ownerToken) {
      PROCESS_REPO_OWNERS.delete(canonicalStorageDir);
    }
    try { crossProcessOwner.release(); } catch {}
    throw error;
  }

  return Object.freeze({
    get installationAuthority() { return state.installationAuthority; },
    assertOwnership,
    releaseOwnership({abandonActive = false} = {}) {
      assertOwnership();
      if (!abandonActive && processOwner.hasActive()) {
        throw new Error("SDK operation storage ownership cannot be released with active operations.");
      }
      ownershipReleased = true;
      if (PROCESS_REPO_OWNERS.get(canonicalStorageDir)?.token === ownerToken) {
        PROCESS_REPO_OWNERS.delete(canonicalStorageDir);
        crossProcessOwner.release();
      }
    },
    reservePreparedTerminal(operationId) {
      assertOwnership();
      const existing = state.operations[operationId];
      if (!existing || TERMINAL_STATUSES.has(existing.public.status)) throw new Error("Prepared terminal reserve requires one active durable operation.");
      const current = readPreparedReserve();
      if (current) {
        if (current.operationId === operationId && current.state === "reserved") return true;
        throw new Error("Prepared terminal durable capacity is already reserved.");
      }
      writePreparedReserve({version: 1, state: "reserved", operationId}, {exclusive: true});
      return true;
    },
    bindPreparedActionRequest(operationId, request) {
      assertOwnership();
      const existing = state.operations[operationId];
      if (!existing || TERMINAL_STATUSES.has(existing.public.status)) throw new Error("Prepared request binding requires one active durable operation.");
      const parsed = sdkPrepareActionRequestSchema.parse(request);
      const nextRecord = structuredClone(existing);
      nextRecord.private.preparedActionRequest = parsed;
      const validated = validatePrivateRecord(nextRecord, operationId, state.installationAuthority);
      commit({...state, operations: {...state.operations, [operationId]: validated}});
      return structuredClone(parsed);
    },
    readPreparedTerminalJournal(operationId) {
      const journal = readPreparedReserve();
      return journal?.version === 1 && journal.state === "operation_record" && journal.operationId === operationId
        ? sdkPreparedActionTerminalSchema.parse(journal.record?.private?.preparedActionTerminal)
        : null;
    },
    cleanup(at = Date.now()) {
      const cleaned = cleanupState(state, at);
      if (cleaned) commit(cleaned);
    },
    getOperation(operationId, { cleanupAt = Date.now() } = {}) {
      cleanupTarget(operationId, null, cleanupAt);
      const record = state.operations[operationId];
      return record ? structuredClone(record) : null;
    },
    getReservation(accountFingerprint, key, { cleanupAt = Date.now() } = {}) {
      const storageKey = reservationStorageKey(accountFingerprint, key);
      const current = state.idempotency[storageKey];
      if (current) cleanupTarget(current.operationId, storageKey, cleanupAt);
      const reservation = state.idempotency[storageKey];
      if (reservation) {
        assertReservationMatchesOperation(reservation, state.operations[reservation.operationId], storageKey);
      }
      return reservation ? structuredClone(reservation) : null;
    },
    createOperationAtomic(record, reservation = null) {
      const validated = validatePrivateRecord(
        record,
        record?.public?.operationId,
        state.installationAuthority,
      );
      const operationId = validated.public.operationId;
      if (state.operations[operationId]) throw new Error("SDK operation identity collision.");
      let idempotency = state.idempotency;
      if (reservation) {
        const storageKey = reservationStorageKey(reservation.accountFingerprint, reservation.key);
        if (idempotency[storageKey]) throw new Error("SDK idempotency reservation collision.");
        const validatedReservation = validateReservation(reservation, storageKey, state.installationAuthority);
        assertReservationMatchesOperation(validatedReservation, validated, storageKey);
        idempotency = {...idempotency, [storageKey]: validatedReservation};
      }
      commit({
        ...state,
        operations: {...state.operations, [operationId]: validated},
        idempotency,
      });
      return structuredClone(validated);
    },
    retainForWorkflow(operationId, accountFingerprint, retentionExpiresAt) {
      const existing = state.operations[operationId];
      if (!existing
        || existing.private.accountFingerprint !== accountFingerprint
        || existing.private.installationAuthority !== state.installationAuthority) {
        return null;
      }
      const expiresAt = Date.parse(retentionExpiresAt);
      if (!Number.isFinite(expiresAt)) throw new Error("SDK workflow operation retention is invalid.");
      const current = Date.parse(existing.private.workflowRetentionExpiresAt ?? "");
      if (Number.isFinite(current) && current >= expiresAt) return structuredClone(existing);
      const retained = structuredClone(existing);
      retained.private.workflowRetentionExpiresAt = new Date(expiresAt).toISOString();
      commit({...state, operations: {...state.operations, [operationId]: retained}});
      return structuredClone(state.operations[operationId]);
    },
    transition(operationId, expectedSequence, updater, {durable = true} = {}) {
      const existing = state.operations[operationId];
      if (!existing) return null;
      if (existing.public.sequence !== expectedSequence) return false;
      if (TERMINAL_STATUSES.has(existing.public.status)) {
        return false;
      }
      const nextValue = updater(structuredClone(existing));
      if (!nextValue) return false;
      const validated = durable
        ? validatePrivateRecord(nextValue, operationId, state.installationAuthority)
        : {
            public: sdkOperationSnapshotSchema.parse(nextValue.public),
            private: existing.private,
          };
      if (validated.public.sequence !== expectedSequence + 1) {
        throw new Error("SDK operation transition must advance authority sequence exactly once.");
      }
      assertStatusTransition(existing.public.status, validated.public.status);
      if ((validated.public.idempotency?.key ?? null) !== (existing.public.idempotency?.key ?? null)) {
        throw new Error("SDK operation transition cannot change its idempotency binding.");
      }
      let idempotency = state.idempotency;
      if ("retentionExpiresAt" in validated.public) {
        const idempotencyKey = validated.public.idempotency?.key;
        if (idempotencyKey) {
          const storageKey = reservationStorageKey(validated.private.accountFingerprint, idempotencyKey);
          const currentReservation = idempotency[storageKey];
          if (!currentReservation) {
            throw new Error(`Retained SDK operation is missing its idempotency reservation: ${operationId}`);
          }
          const reservation = {
            ...currentReservation,
            resultExpiresAt: Date.parse(validated.public.retentionExpiresAt),
            tombstoneExpiresAt: Date.parse(validated.public.idempotency.tombstoneExpiresAt),
          };
          assertReservationMatchesOperation(reservation, validated, storageKey);
          idempotency = {...idempotency, [storageKey]: reservation};
        }
      }
      const draft = {
        ...state,
        operations: {...state.operations, [operationId]: validated},
        idempotency,
      };
      if (!durable) {
        if (!["running", "waiting"].includes(existing.public.status)
          || !["running", "waiting"].includes(validated.public.status)
          || "retentionExpiresAt" in validated.public
          || JSON.stringify(withoutIntermediateProgress(validated.public))
            !== JSON.stringify(withoutIntermediateProgress(existing.public))
          || idempotency !== state.idempotency) {
          throw new Error("Only intermediate SDK operation progress may be non-durable.");
        }
        state = draft;
        return structuredClone(validated);
      }
      try {
        commit(draft);
      } catch (error) {
        const reserve = readPreparedReserve();
        if (reserve?.operationId === operationId && "retentionExpiresAt" in validated.public) {
          writePreparedReserve({version: 1, state: "operation_record", operationId, record: validated});
          state = draft;
          return structuredClone(validated);
        }
        throw error;
      }
      if ("retentionExpiresAt" in validated.public) {
        const reserve = readPreparedReserve();
        if (reserve?.operationId === operationId) fs.unlinkSync(preparedReservePath);
      }
      return structuredClone(validated);
    },
    listActive() {
      return Object.values(state.operations)
        .filter((record) => !TERMINAL_STATUSES.has(record.public.status))
        .map((record) => structuredClone(record));
    },
    inspect() {
      return structuredClone(state);
    },
  });
}
