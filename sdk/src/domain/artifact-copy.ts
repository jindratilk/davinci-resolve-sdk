import { createHash } from "node:crypto";
import { link, lstat, mkdtemp, open, rmdir, unlink, type FileHandle } from "node:fs/promises";
import path from "node:path";

const CHUNK_BYTES = 1024 * 1024;
const UNSUPPORTED_LINK = new Set(["ENOTSUP", "EOPNOTSUPP", "ENOSYS"]);

type CopyRequest = Readonly<{
  destinationPath: string;
  sizeBytes: number;
  sha256: string;
  readChunk(offset: number, length: number): Promise<Uint8Array>;
  invalidResponse(message: string): Error;
}>;

type FileIdentity = Awaited<ReturnType<typeof identity>>;

async function identity(handle: FileHandle) {
  return handle.stat({ bigint: true });
}

function matches(left: FileIdentity, right: FileIdentity): boolean {
  return left.isFile() && right.isFile() && left.ino > 0n && right.ino > 0n
    && left.dev === right.dev && left.ino === right.ino;
}

async function writeAll(handle: FileHandle, bytes: Uint8Array, position: number, request: CopyRequest) {
  let written = 0;
  while (written < bytes.length) {
    const result = await handle.write(bytes, written, bytes.length - written, position + written);
    if (!Number.isInteger(result.bytesWritten) || result.bytesWritten < 1 || result.bytesWritten > bytes.length - written) {
      throw request.invalidResponse("Artifact destination stopped before the verified chunk was written.");
    }
    written += result.bytesWritten;
  }
}

async function verifyFile(handle: FileHandle, request: CopyRequest): Promise<FileIdentity> {
  await handle.sync();
  const before = await identity(handle);
  if (!matches(before, before) || before.size !== BigInt(request.sizeBytes)) {
    throw request.invalidResponse("Copied artifact size or file identity did not match its verified output.");
  }
  const hash = createHash("sha256");
  const buffer = Buffer.alloc(Math.min(CHUNK_BYTES, request.sizeBytes));
  let offset = 0;
  while (offset < request.sizeBytes) {
    const length = Math.min(buffer.length, request.sizeBytes - offset);
    const result = await handle.read(buffer, 0, length, offset);
    if (result.bytesRead !== length) throw request.invalidResponse("Copied artifact ended before its verified size.");
    hash.update(buffer.subarray(0, result.bytesRead));
    offset += result.bytesRead;
  }
  const after = await identity(handle);
  if (!matches(before, after) || after.size !== before.size || after.mtimeNs !== before.mtimeNs
    || `sha256:${hash.digest("hex")}` !== request.sha256) {
    throw request.invalidResponse("Copied artifact content did not match its verified digest.");
  }
  return after;
}

async function verifyPath(destination: string, expected: FileIdentity, request: CopyRequest) {
  const current = await lstat(destination, { bigint: true });
  if (!matches(current, expected) || current.size !== expected.size) {
    throw request.invalidResponse("Artifact destination was replaced before copy completion.");
  }
}

async function publishWithoutLinks(stagedPath: string, stagedIdentity: FileIdentity, request: CopyRequest) {
  // Some filesystems cannot hard-link. This fallback preserves no-overwrite
  // and user data, but a failed copy may leave its newly created partial file.
  // Never unlink the caller's pathname: it may now belong to another writer.
  const source = await open(stagedPath, "r");
  let destination: FileHandle | undefined;
  try {
    if (!matches(await identity(source), stagedIdentity)) {
      throw request.invalidResponse("Verified artifact staging was replaced before publication.");
    }
    destination = await open(request.destinationPath, "wx+", 0o600);
    const buffer = Buffer.alloc(Math.min(CHUNK_BYTES, request.sizeBytes));
    let offset = 0;
    while (offset < request.sizeBytes) {
      const length = Math.min(buffer.length, request.sizeBytes - offset);
      const result = await source.read(buffer, 0, length, offset);
      if (result.bytesRead !== length) throw request.invalidResponse("Verified artifact staging ended unexpectedly.");
      await writeAll(destination, buffer.subarray(0, length), offset, request);
      offset += length;
    }
    const publishedIdentity = await verifyFile(destination, request);
    // Keep the descriptor open during pathname comparison to pin its inode.
    await verifyPath(request.destinationPath, publishedIdentity, request);
    await destination.close();
    destination = undefined;
  } finally {
    await destination?.close().catch(() => {});
    await source.close().catch(() => {});
  }
}

/** Write and verify private content before publishing a new caller-owned file. @internal */
export async function copyVerifiedArtifact(request: CopyRequest): Promise<void> {
  if (typeof request.destinationPath !== "string" || !path.isAbsolute(request.destinationPath)) {
    throw new TypeError("Artifact destinationPath must be absolute.");
  }
  // This is an early rejection only; exclusive publication remains authoritative.
  try {
    await lstat(request.destinationPath);
    throw Object.assign(new Error("Artifact destination already exists."), { code: "EEXIST" });
  } catch (error) {
    if ((error as NodeJS.ErrnoException)?.code !== "ENOENT") throw error;
  }
  const directory = await mkdtemp(path.join(path.dirname(request.destinationPath), ".cutagent-artifact-"));
  const stagedPath = path.join(directory, "content");
  let staged: FileHandle | undefined;
  try {
    staged = await open(stagedPath, "wx+", 0o600);
    let offset = 0;
    while (offset < request.sizeBytes) {
      const bytes = await request.readChunk(offset, Math.min(CHUNK_BYTES, request.sizeBytes - offset));
      if (bytes.length < 1 || offset + bytes.length > request.sizeBytes) {
        throw request.invalidResponse("CutAgent runtime returned inconsistent artifact content.");
      }
      await writeAll(staged, bytes, offset, request);
      offset += bytes.length;
    }
    const stagedIdentity = await verifyFile(staged, request);
    await staged.close();
    staged = undefined;
    await verifyPath(stagedPath, stagedIdentity, request);
    try {
      await link(stagedPath, request.destinationPath);
    } catch (error) {
      if (!UNSUPPORTED_LINK.has((error as NodeJS.ErrnoException)?.code ?? "")) throw error;
      await publishWithoutLinks(stagedPath, stagedIdentity, request);
      return;
    }
    await verifyPath(request.destinationPath, stagedIdentity, request);
  } finally {
    await staged?.close().catch(() => {});
    // Only private paths created by this call are cleanup targets.
    await unlink(stagedPath).catch(() => {});
    await rmdir(directory).catch(() => {});
  }
}
