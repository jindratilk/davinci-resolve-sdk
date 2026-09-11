import crypto from "node:crypto";
import path from "node:path";
import { lstat, realpath } from "node:fs/promises";
import {
  sdkMediaPoolImportInputSchema,
  sdkMediaPoolImportResultSchema,
  sdkProjectContextMutationResultSchema,
  sdkProjectCreateInputSchema,
} from "../contracts/generated/sdk-project-media.js";

function digest(value) {
  return `sha256:${crypto.createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex")}`;
}

function evidence(modality, summary, value) {
  return {
    evidenceId: `evidence_${crypto.randomUUID()}`,
    modality,
    summary,
    capturedAt: new Date().toISOString(),
    digest: digest(value),
  };
}

function failure(code, message, context, possibleMutation = "none", usage = possibleMutation === "none" ? "released" : "unknown") {
  return {
    kind: code === "STALE_REVISION" ? "stale_revision"
      : code === "CAPABILITY_UNAVAILABLE" ? "capability_unavailable"
        : code === "VERIFICATION_FAILED" ? "verification_failed" : "operation_failed",
    code,
    message,
    retrySafe: false,
    possibleMutation,
    usage,
    recovery: possibleMutation === "none" ? ["inspect_state"] : ["inspect_state", "manual_recovery"],
    recoveryGuidance: [possibleMutation === "none" ? "Inspect the current project context and acquire a fresh revision." : "Inspect the current project context before any further mutation."],
    readbackRequired: possibleMutation !== "none",
    requestId: context.requestId,
    operationId: context.operationId,
    executionId: context.executionId,
  };
}

function sameLibrary(left, right) {
  return left !== null && right !== null && left.name === right.name && left.kind === right.kind;
}

async function readAllMedia(liveInspectionService, projectId) {
  const firstRequest = { operation: "mediaPool.page", projectId, offset: 0, pageSize: 32, expectedRevision: null, search: null };
  const first = await liveInspectionService.readWithMutationGuard(firstRequest, { deadlineAtMs: Date.now() + 60_000 });
  if (!first.privateMediaPoolState || !Array.isArray(first.privateMediaPoolState.entries)) {
    throw new Error("Private complete Media Pool verification state was unavailable.");
  }
  const assets = [...first.value.assets];
  const folders = [...first.value.folders];
  const privateEntries = [...first.privateMediaPoolState.entries];
  const poolDigest = first.privateMediaPoolState.poolDigest;
  let offset = first.value.nextOffset;
  while (offset !== null) {
    const page = await liveInspectionService.readWithMutationGuard({ operation: "mediaPool.page", projectId, offset, pageSize: 32, expectedRevision: first.value.revision, search: null }, { deadlineAtMs: Date.now() + 60_000 });
    if (page.privateMediaPoolState?.poolDigest !== poolDigest || !Array.isArray(page.privateMediaPoolState.entries)) {
      throw new Error("Private Media Pool verification state changed across bounded pages.");
    }
    assets.push(...page.value.assets);
    folders.push(...page.value.folders);
    privateEntries.push(...page.privateMediaPoolState.entries);
    offset = page.value.nextOffset;
  }
  if (privateEntries.length !== first.value.total || assets.length + folders.length !== first.value.total) {
    throw new Error("The bounded Media Pool pages did not materialize the complete inventory.");
  }
  return { ...first, assets, folders, privateEntries, revision: first.value.revision };
}

function stableAsset(asset) {
  return {
    id: asset.id,
    name: asset.name,
    kind: asset.kind,
    sourceFileName: asset.sourceFileName,
    duration: asset.duration,
    resolution: asset.resolution,
    frameRate: asset.frameRate,
    startTimecode: asset.startTimecode,
    metadata: asset.metadata,
  };
}

function regularFileIdentity(fileInfo) {
  return {
    device: fileInfo.dev.toString(),
    inode: fileInfo.ino.toString(),
    size: fileInfo.size.toString(),
    modifiedNanoseconds: fileInfo.mtimeNs.toString(),
  };
}

function sameRegularFileIdentity(left, right) {
  return left.device === right.device
    && left.inode === right.inode
    && left.size === right.size
    && left.modifiedNanoseconds === right.modifiedNanoseconds;
}

async function exactRegularFile(requestedPath) {
  const absolutePath = path.resolve(requestedPath);
  try {
    const before = await lstat(absolutePath, { bigint: true });
    const canonicalPath = await realpath(absolutePath);
    const after = await lstat(canonicalPath, { bigint: true });
    const beforeIdentity = regularFileIdentity(before);
    const afterIdentity = regularFileIdentity(after);
    if (canonicalPath !== absolutePath
      || !before.isFile()
      || before.isSymbolicLink()
      || !after.isFile()
      || after.isSymbolicLink()
      || !sameRegularFileIdentity(beforeIdentity, afterIdentity)) {
      throw new Error("not an exact regular file");
    }
    return { canonicalPath, identity: afterIdentity };
  } catch {
    const error = new Error("Media Pool import accepts existing exact regular files and rejects directories or symbolic-link traversal.");
    error.code = "CAPABILITY_UNAVAILABLE";
    throw error;
  }
}

async function requireUnchangedRegularFile(file) {
  try {
    const current = await lstat(file.canonicalPath, { bigint: true });
    if (!current.isFile() || current.isSymbolicLink()
      || !sameRegularFileIdentity(file.identity, regularFileIdentity(current))) {
      throw new Error("file identity changed");
    }
  } catch {
    const error = new Error("The exact import file changed after inspection.");
    error.code = "STALE_REVISION";
    throw error;
  }
}

function entryMultiset(entries) {
  const counts = new Map();
  for (const entry of entries) {
    const key = digest(entry);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

function sameEntryMultiset(left, right) {
  const leftCounts = entryMultiset(left);
  const rightCounts = entryMultiset(right);
  return leftCounts.size === rightCounts.size
    && [...leftCounts].every(([key, count]) => rightCounts.get(key) === count);
}

function importProtectedEntry(entry) {
  if (entry.entryKind !== "asset") return entry;
  // DaVinci Resolve may select the newly imported item and deselect the
  // previously selected item. That UI selection churn is incidental to this
  // exact import; every durable asset field remains protected below.
  const { selected: _incidentalSelection, ...protectedEntry } = entry;
  return protectedEntry;
}

function sameImportProtectedEntries(left, right) {
  return sameEntryMultiset(
    left.map(importProtectedEntry),
    right.map(importProtectedEntry),
  );
}

function unchangedExecutionFailure(executionError, context, fallbackMessage) {
  const errorCode = executionError?.cli_error_code ?? executionError?.code;
  if (errorCode === "STALE_REVISION") {
    return failure("STALE_REVISION", executionError.message, context);
  }
  if (errorCode === "CAPABILITY_UNAVAILABLE" || errorCode === "CAPABILITY_NEGOTIATION_FAILED") {
    return failure("CAPABILITY_UNAVAILABLE", executionError.message, context);
  }
  return failure("OPERATION_FAILED", executionError?.message ?? fallbackMessage, context);
}

function preExecutionFailure(error, context, fallbackMessage) {
  const terminalFailure = unchangedExecutionFailure(error, context, fallbackMessage);
  return {
    status: "failed",
    possibleMutation: "none",
    usage: terminalFailure.usage,
    failure: terminalFailure,
  };
}

function unchangedMediaExecutionFailure(executionError, context) {
  const errorCode = executionError?.cli_error_code ?? executionError?.code;
  const publicMessage = errorCode === "STALE_REVISION"
      ? "Media Pool import was denied because the inspected state changed."
      : errorCode === "CAPABILITY_UNAVAILABLE" || errorCode === "CAPABILITY_NEGOTIATION_FAILED"
        ? "Media Pool import is unavailable in the current DaVinci Resolve environment."
        : "Media Pool import made no verified change.";
  return unchangedExecutionFailure(
    executionError ? { ...executionError, message: publicMessage } : null,
    context,
    publicMessage,
  );
}

function readbackUnavailableOutcome({ executionError, executionMayHaveStarted, context, subject, unchangedFailure = unchangedExecutionFailure }) {
  const verification = {
    outcome: "failed",
    summary: `${subject} readback was unavailable.`,
    evidence: [evidence("readback", `Could not read back ${subject.toLowerCase()} after the execution boundary.`, { available: false })],
    protectedStatePreserved: null,
  };
  if (executionMayHaveStarted) {
    return {
      status: "verification_failed",
      possibleMutation: "possible",
      usage: "consumed",
      failure: failure("VERIFICATION_FAILED", `${subject} readback was unavailable after execution started.`, context, "possible", "consumed"),
      verification,
    };
  }
  const terminalFailure = unchangedFailure(executionError, context, `${subject} execution did not start and readback was unavailable.`);
  return {
    status: "failed",
    possibleMutation: "none",
    usage: terminalFailure.usage,
    failure: terminalFailure,
    verification,
  };
}

/** Build the accepted exact project/media executors available in this release. */
export function createSdkProjectMediaActions({ liveInspectionService, resolveService }) {
  if (typeof liveInspectionService?.readWithMutationGuard !== "function") throw new TypeError("Project actions require guarded live project-context inspection.");
  if (typeof resolveService?.executeSdkProjectCreate !== "function") throw new TypeError("Project actions require the CutAgent CLI mutation boundary.");
  if (typeof resolveService?.executeSdkMediaImport !== "function") throw new TypeError("Media actions require the CutAgent CLI mutation boundary.");

  return {
    "cutagent.action.project.create": {
      inputSchema: sdkProjectCreateInputSchema,
      resultSchema: sdkProjectContextMutationResultSchema,
      idempotency: "required",
      async execute(context, rawInput) {
        const input = sdkProjectCreateInputSchema.parse(rawInput);
        if (input.mediaLocation !== undefined && input.mediaLocation !== null
          && typeof resolveService.readSdkProjectSettings !== "function") {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("CAPABILITY_UNAVAILABLE", "Custom Project media locations require project-settings readback.", context) };
        }
        let inspected;
        try {
          inspected = await liveInspectionService.readWithMutationGuard({ operation: "project.context" }, { deadlineAtMs: Date.now() + 60_000 });
        } catch (error) {
          return preExecutionFailure(error, context, "Project-context inspection failed before creation dispatch.");
        }
        const before = inspected.value;
        if (before.projectRevision.status !== "available" || before.projectRevision.revision !== input.precondition) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The project context changed after inspection.", context) };
        }
        if (before.library === null || before.library.kind !== "disk") {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("CAPABILITY_UNAVAILABLE", "Project creation currently requires an inspected Disk project library.", context) };
        }
        let executionMayHaveStarted = false;
        let executionError = null;
        try {
          await resolveService.executeSdkProjectCreate(input, {
            mutationGuard: inspected.mutationGuard,
            onSpawnAttempt() {
              context.reportExecutionStarted();
              executionMayHaveStarted = true;
            },
          });
          executionMayHaveStarted = true;
        } catch (error) { executionError = error; }
        let after;
        try { after = (await liveInspectionService.readWithMutationGuard({ operation: "project.context" }, { deadlineAtMs: Date.now() + 60_000 })).value; } catch {
          return readbackUnavailableOutcome({ executionError, executionMayHaveStarted, context, subject: "Project-context" });
        }
        const changed = digest(before) !== digest(after);
        let mediaLocationMatched = input.mediaLocation === undefined || input.mediaLocation === null;
        let mediaLocationReadback = null;
        if (!mediaLocationMatched && executionError === null) {
          try {
            mediaLocationReadback = await resolveService.readSdkProjectSettings();
            mediaLocationMatched = mediaLocationReadback?.projectMediaLocation === input.mediaLocation;
          } catch {}
        }
        const matched = executionError === null && changed
          && sameLibrary(before.library, after.library)
          && after.project?.name === input.name
          && after.project?.id !== null
          && after.projectRevision.status === "available"
          && after.projectRevision.revision !== input.precondition
          && mediaLocationMatched;
        const report = {
          outcome: matched ? "passed" : "failed",
          summary: matched ? "The exact created project and unchanged project library matched independent readback." : "Project creation did not match authoritative context readback.",
          evidence: [evidence("readback", "Read back the complete project context after creation.", after), evidence("structural", "Compared the project-library identity before and after creation.", { before: before.library, after: after.library }), ...(input.mediaLocation === undefined || input.mediaLocation === null ? [] : [evidence("readback", "Read back the exact custom Project media location.", { projectMediaLocation: mediaLocationReadback?.projectMediaLocation ?? null })])],
          protectedStatePreserved: sameLibrary(before.library, after.library),
        };
        if (matched) {
          return { status: "succeeded", possibleMutation: "confirmed", usage: "consumed", verification: report, result: { changed: true, context: after } };
        }
        if (!changed) {
          if (executionMayHaveStarted) {
            return { status: "failed", possibleMutation: "possible", usage: "consumed", failure: failure("OPERATION_FAILED", "Project creation made no verified change after execution started.", context, "possible", "consumed"), verification: report };
          }
          const terminalFailure = unchangedExecutionFailure(executionError, context, "Project creation made no verified change.");
          return { status: "failed", possibleMutation: "none", usage: terminalFailure.usage, failure: terminalFailure, verification: report };
        }
        if (!executionMayHaveStarted) {
          const terminalFailure = unchangedExecutionFailure(executionError, context, "Project creation did not start; the project context changed independently.");
          return { status: "failed", possibleMutation: "none", usage: terminalFailure.usage, failure: terminalFailure, verification: report };
        }
        return { status: "verification_failed", possibleMutation: "possible", usage: "consumed", failure: failure("VERIFICATION_FAILED", executionError?.message ?? "Project creation produced an unexpected project context.", context, "possible", "consumed"), verification: report };
      },
    },
    "cutagent.action.media.import": {
      inputSchema: sdkMediaPoolImportInputSchema,
      resultSchema: sdkMediaPoolImportResultSchema,
      idempotency: "required",
      async execute(context, rawInput) {
        const input = sdkMediaPoolImportInputSchema.parse(rawInput);
        let importFiles;
        try { importFiles = await Promise.all(input.paths.map(exactRegularFile)); } catch (error) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("CAPABILITY_UNAVAILABLE", error.message, context) };
        }
        if (new Set(importFiles.map((file) => file.canonicalPath)).size !== importFiles.length) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("CAPABILITY_UNAVAILABLE", "Media Pool import paths must resolve to distinct exact files.", context) };
        }
        let projectContext;
        try {
          projectContext = await liveInspectionService.readWithMutationGuard({ operation: "project.context" }, { deadlineAtMs: Date.now() + 60_000 });
        } catch (error) {
          return preExecutionFailure(error, context, "Project-context inspection failed before Media Pool import dispatch.");
        }
        if (projectContext.value.project?.id !== input.projectId || projectContext.value.projectRevision.status !== "available") {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The exact current project changed before Media Pool import.", context) };
        }
        let before;
        try {
          before = await readAllMedia(liveInspectionService, input.projectId);
        } catch (error) {
          return preExecutionFailure(error, context, "Media Pool inspection failed before import dispatch.");
        }
        if (before.revision !== input.precondition) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The Media Pool changed after inspection.", context) };
        }
        const destination = input.destination.kind === "root"
          ? before.privateEntries.find((entry) => entry.entryKind === "folder" && JSON.stringify(entry.coordinate) === "[0]")
          : before.privateEntries.find((entry) => entry.entryKind === "folder" && entry.id === input.destination.id);
        if (!destination || !Array.isArray(destination.coordinate)
          || (input.destination.kind === "folder" && !destination.nativeId)) {
          return { status: "failed", possibleMutation: "none", usage: "released", failure: failure("STALE_REVISION", "The exact destination Media Pool bin is no longer available.", context) };
        }
        let executionMayHaveStarted = false;
        let executionError = null;
        try {
          await Promise.all(importFiles.map(requireUnchangedRegularFile));
          liveInspectionService.invalidateMediaPoolSnapshots?.(input.projectId);
          await resolveService.executeSdkMediaImport(importFiles.map((file) => file.canonicalPath), {
            mutationGuard: before.mutationGuard,
            extraEnv: {
              CUTAGENT_SDK_MEDIA_IMPORT_FILES: JSON.stringify(importFiles.map((file) => ({ path: file.canonicalPath, identity: file.identity }))),
              CUTAGENT_SDK_MEDIA_IMPORT_DESTINATION: JSON.stringify({ coordinate: destination.coordinate, nativeId: destination.nativeId ?? null }),
            },
            onSpawnAttempt() {
              context.reportExecutionStarted();
              executionMayHaveStarted = true;
            },
          });
          executionMayHaveStarted = true;
        } catch (error) { executionError = error; }
        let after;
        try { after = await readAllMedia(liveInspectionService, input.projectId); } catch {
          return readbackUnavailableOutcome({
            executionError,
            executionMayHaveStarted,
            context,
            subject: "Media Pool",
            unchangedFailure: unchangedMediaExecutionFailure,
          });
        }
        const beforeDurableIds = new Set(before.privateEntries.filter((entry) => entry.entryKind === "asset" && entry.id !== null).map((entry) => entry.id));
        const importedPrivate = after.privateEntries.filter((entry) => entry.entryKind === "asset"
          && entry.id !== null
          && !beforeDurableIds.has(entry.id)
          && importFiles.some((file) => file.canonicalPath === entry.sourcePath)
          && JSON.stringify(entry.folderCoordinate) === JSON.stringify(destination.coordinate));
        const importedIds = new Set(importedPrivate.map((entry) => entry.id));
        const imported = importFiles.map((file) => {
          const privateEntry = importedPrivate.find((entry) => entry.sourcePath === file.canonicalPath);
          return privateEntry ? after.assets.find((asset) => asset.id === privateEntry.id) : undefined;
        }).filter(Boolean);
        const afterProtectedEntries = after.privateEntries.filter((entry) => !importedIds.has(entry.id));
        const everyPathImportedOnce = importFiles.every((file) => importedPrivate.filter((entry) => entry.sourcePath === file.canonicalPath).length === 1);
        const existingPreserved = everyPathImportedOnce
          && importedPrivate.length === importFiles.length
          && after.privateEntries.length === before.privateEntries.length + importFiles.length
          && sameImportProtectedEntries(before.privateEntries, afterProtectedEntries);
        const matched = executionError === null && after.revision !== before.revision && existingPreserved && imported.length === importFiles.length;
        const report = {
          outcome: matched ? "passed" : "failed",
          summary: matched ? "Every exact requested file produced one new durable Media Pool item in the requested bin and existing assets were preserved." : "Media Pool import did not match authoritative closed-world readback.",
          evidence: [evidence("readback", "Correlated each exact private source path, durable item identity, and requested-folder membership after import.", { revision: after.revision, imported: importedPrivate }), evidence("structural", "Compared every pre-existing folder and every durable asset field; Media Pool selection changes caused by the import were treated as incidental.", { before: before.privateEntries, after: afterProtectedEntries, existingPreserved })],
          protectedStatePreserved: existingPreserved,
        };
        if (matched) {
          return {
            status: "succeeded",
            possibleMutation: "confirmed",
            usage: "consumed",
            verification: report,
            result: {
              projectId: input.projectId,
              assets: imported.map((asset) => ({ id: asset.id, snapshotId: asset.snapshotId, name: asset.name })),
              revision: after.revision,
            },
          };
        }
        if (after.revision === before.revision) {
          if (executionMayHaveStarted) {
            return { status: "failed", possibleMutation: "possible", usage: "consumed", failure: failure("OPERATION_FAILED", "Media Pool import made no verified change after execution started.", context, "possible", "consumed"), verification: report };
          }
          const terminalFailure = unchangedMediaExecutionFailure(executionError, context);
          return { status: "failed", possibleMutation: "none", usage: terminalFailure.usage, failure: terminalFailure, verification: report };
        }
        if (!executionMayHaveStarted) {
          const terminalFailure = unchangedMediaExecutionFailure(executionError, context);
          return { status: "failed", possibleMutation: "none", usage: terminalFailure.usage, failure: terminalFailure, verification: report };
        }
        return { status: "verification_failed", possibleMutation: "possible", usage: "consumed", failure: failure("VERIFICATION_FAILED", "Media Pool import produced an unexpected state.", context, "possible", "consumed"), verification: report };
      },
    },
  };
}
