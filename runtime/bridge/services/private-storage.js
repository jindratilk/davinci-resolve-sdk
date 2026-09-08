import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { randomUUID } from "node:crypto";

export const PRIVATE_DIR_MODE = 0o700;
export const PRIVATE_FILE_MODE = 0o600;
export const PRIVATE_EXECUTABLE_MODE = 0o700;

function pathIsInside(parent, child) {
  const relative = path.relative(parent, child);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function expectedCanonicalPath(absolutePath) {
  const temporaryRoot = path.resolve(os.tmpdir());
  if (!pathIsInside(temporaryRoot, absolutePath)) return absolutePath;
  const canonicalTemporaryRoot = fs.realpathSync(temporaryRoot);
  return path.join(canonicalTemporaryRoot, path.relative(temporaryRoot, absolutePath));
}

function isTrustedTemporaryPrefix(componentPath) {
  const temporaryRoot = path.resolve(os.tmpdir());
  return pathIsInside(componentPath, temporaryRoot);
}

function sameFileIdentity(left, right) {
  return left?.dev === right?.dev && left?.ino === right?.ino;
}

function assertCanonicalDirectoryPath(directoryPath, label) {
  const absolutePath = path.resolve(directoryPath);
  const parsed = path.parse(absolutePath);
  let currentPath = parsed.root;
  for (const component of absolutePath.slice(parsed.root.length).split(path.sep).filter(Boolean)) {
    currentPath = path.join(currentPath, component);
    const stat = fs.lstatSync(currentPath);
    const trustedTemporaryPrefix = isTrustedTemporaryPrefix(currentPath);
    if (
      (stat.isSymbolicLink() && !trustedTemporaryPrefix)
      || (!stat.isSymbolicLink() && !stat.isDirectory())
      || (
        !trustedTemporaryPrefix
        && fs.realpathSync(currentPath) !== expectedCanonicalPath(currentPath)
      )
    ) {
      throw new Error(`${label} must not traverse symlinked path components.`);
    }
  }
  return absolutePath;
}

export function assertCanonicalPrivateDirectory(directoryPath, {
  label = "Managed private directory",
} = {}) {
  if (typeof directoryPath !== "string" || !directoryPath.trim()) {
    throw new Error(`${label} requires a directory path.`);
  }
  return assertCanonicalDirectoryPath(directoryPath, label);
}

export function ensureCanonicalPrivateDirectory(directoryPath, {
  label = "Managed private directory",
} = {}) {
  if (typeof directoryPath !== "string" || !directoryPath.trim()) {
    throw new Error(`${label} requires a directory path.`);
  }
  const absolutePath = path.resolve(directoryPath);
  const parsed = path.parse(absolutePath);
  let currentPath = parsed.root;
  for (const component of absolutePath.slice(parsed.root.length).split(path.sep).filter(Boolean)) {
    currentPath = path.join(currentPath, component);
    let stat;
    try {
      stat = fs.lstatSync(currentPath);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
      try {
        fs.mkdirSync(currentPath, { mode: PRIVATE_DIR_MODE });
      } catch (mkdirError) {
        if (mkdirError?.code !== "EEXIST") throw mkdirError;
      }
      stat = fs.lstatSync(currentPath);
    }
    const trustedTemporaryPrefix = isTrustedTemporaryPrefix(currentPath);
    if (
      (stat.isSymbolicLink() && !trustedTemporaryPrefix)
      || (!stat.isSymbolicLink() && !stat.isDirectory())
      || (
        !trustedTemporaryPrefix
        && fs.realpathSync(currentPath) !== expectedCanonicalPath(currentPath)
      )
    ) {
      throw new Error(`${label} must not traverse symlinked path components.`);
    }
  }

  const noFollow = Number.isInteger(fs.constants.O_NOFOLLOW) ? fs.constants.O_NOFOLLOW : 0;
  const directoryOnly = Number.isInteger(fs.constants.O_DIRECTORY) ? fs.constants.O_DIRECTORY : 0;
  if (process.platform === "win32") {
    try { fs.chmodSync(absolutePath, PRIVATE_DIR_MODE); } catch { /* ACL ownership is inherited. */ }
    return assertCanonicalDirectoryPath(absolutePath, label);
  }
  const descriptor = fs.openSync(absolutePath, fs.constants.O_RDONLY | directoryOnly | noFollow);
  try {
    const openedStat = fs.fstatSync(descriptor);
    const pathStat = fs.lstatSync(absolutePath);
    if (
      !openedStat.isDirectory()
      || pathStat.isSymbolicLink()
      || !sameFileIdentity(openedStat, pathStat)
      || fs.realpathSync(absolutePath) !== expectedCanonicalPath(absolutePath)
    ) {
      throw new Error(`${label} changed during secure initialization.`);
    }
    fs.fchmodSync(descriptor, PRIVATE_DIR_MODE);
  } finally {
    fs.closeSync(descriptor);
  }
  return absolutePath;
}

export function ensurePrivateDirectory(directoryPath) {
  if (typeof directoryPath !== "string" || !directoryPath.trim()) {
    throw new Error("ensurePrivateDirectory requires a directory path.");
  }
  fs.mkdirSync(directoryPath, { recursive: true, mode: PRIVATE_DIR_MODE });
  try {
    fs.chmodSync(directoryPath, PRIVATE_DIR_MODE);
  } catch {
    // Best-effort on filesystems that do not expose POSIX modes.
  }
}

export function chmodPrivateFile(filePath, mode = PRIVATE_FILE_MODE) {
  try {
    fs.chmodSync(filePath, mode);
  } catch {
    // Best-effort on filesystems that do not expose POSIX modes.
  }
}

export function writePrivateFileSync(filePath, contents, { mode = PRIVATE_FILE_MODE } = {}) {
  ensurePrivateDirectory(path.dirname(filePath));
  fs.writeFileSync(filePath, contents, { mode });
  chmodPrivateFile(filePath, mode);
}

export function writePrivateJsonAtomic(filePath, value, { mode = PRIVATE_FILE_MODE } = {}) {
  ensurePrivateDirectory(path.dirname(filePath));
  const tempPath = `${filePath}.${randomUUID()}.tmp`;
  fs.writeFileSync(tempPath, JSON.stringify(value, null, 2), { mode });
  chmodPrivateFile(tempPath, mode);
  fs.renameSync(tempPath, filePath);
  chmodPrivateFile(filePath, mode);
}

/**
 * Crash-durable atomic JSON replacement for authorities whose acknowledged
 * state must survive process or machine loss. The file and containing
 * directory are synchronized before the call returns.
 */
export function writePrivateJsonDurableAtomic(filePath, value, { mode = PRIVATE_FILE_MODE } = {}) {
  assertCanonicalPrivateDirectory(path.dirname(filePath), { label: "Durable private storage directory" });
  const tempPath = `${filePath}.${randomUUID()}.tmp`;
  let fileDescriptor;
  try {
    fileDescriptor = fs.openSync(tempPath, "wx", mode);
    fs.writeFileSync(fileDescriptor, JSON.stringify(value, null, 2), "utf8");
    fs.fsyncSync(fileDescriptor);
  } finally {
    if (fileDescriptor !== undefined) fs.closeSync(fileDescriptor);
  }
  chmodPrivateFile(tempPath, mode);
  fs.renameSync(tempPath, filePath);
  chmodPrivateFile(filePath, mode);
  let directoryDescriptor;
  try {
    directoryDescriptor = fs.openSync(path.dirname(filePath), "r");
    fs.fsyncSync(directoryDescriptor);
  } catch (error) {
    const unsupportedOnWindows = process.platform === "win32"
      && ["EACCES", "EBADF", "EISDIR", "EINVAL", "EPERM"].includes(error?.code);
    if (!unsupportedOnWindows) throw error;
  } finally {
    if (directoryDescriptor !== undefined) fs.closeSync(directoryDescriptor);
  }
}

export function writePrivateJsonLinesAtomic(filePath, values, { mode = PRIVATE_FILE_MODE } = {}) {
  ensurePrivateDirectory(path.dirname(filePath));
  const tempPath = `${filePath}.${randomUUID()}.tmp`;
  fs.writeFileSync(tempPath, values.map((value) => JSON.stringify(value)).join("\n") + "\n", { mode });
  chmodPrivateFile(tempPath, mode);
  fs.renameSync(tempPath, filePath);
  chmodPrivateFile(filePath, mode);
}

export function appendPrivateFileSync(filePath, contents, { mode = PRIVATE_FILE_MODE } = {}) {
  ensurePrivateDirectory(path.dirname(filePath));
  const fd = fs.openSync(filePath, "a", mode);
  try {
    fs.writeSync(fd, contents);
  } finally {
    fs.closeSync(fd);
  }
  chmodPrivateFile(filePath, mode);
}
