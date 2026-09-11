import test, { mock } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { syncBuiltinESMExports } from "node:module";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const bundled = await build({
  entryPoints: [fileURLToPath(new URL("../sdk/src/domain/artifact-copy.ts", import.meta.url))],
  bundle: true, platform: "node", format: "esm", write: false,
});
const { copyVerifiedArtifact } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString("base64")}`);
const bytes = Buffer.from("a fully verified artifact\n");
const digest = `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

async function ownedTest(run) {
  const directory = await fs.mkdtemp(path.join(tmpdir(), "cutagent-artifact-publication-test-"));
  const destination = path.join(directory, "delivered.bin");
  const request = {
    destinationPath: destination, sizeBytes: bytes.length, sha256: digest,
    readChunk: async (offset, length) => bytes.subarray(offset, offset + length),
    invalidResponse: (message) => new Error(message),
  };
  try { await run({ directory, destination, request }); }
  finally { mock.restoreAll(); syncBuiltinESMExports(); await fs.rm(directory, { recursive: true, force: true }); }
}

function noLinks(code) {
  mock.method(fs, "link", async () => { throw Object.assign(new Error("controlled link failure"), { code }); });
  syncBuiltinESMExports();
}

test("artifact publication rejects invalid staged bytes without creating final output", () => ownedTest(async ({ directory, destination, request }) => {
  await assert.rejects(copyVerifiedArtifact({ ...request, sha256: `sha256:${"0".repeat(64)}` }), /verified digest/);
  await assert.rejects(fs.stat(destination), { code: "ENOENT" });
  assert.deepEqual(await fs.readdir(directory), []);
}));

test("artifact publication preserves replacement after successful hard-link publication", () => ownedTest(async ({ directory, destination, request }) => {
  const link = fs.link;
  mock.method(fs, "link", async (...args) => {
    await link(...args);
    await fs.unlink(destination);
    await fs.writeFile(destination, "replacement after publication", { flag: "wx" });
  });
  syncBuiltinESMExports();
  await assert.rejects(copyVerifiedArtifact(request), /destination was replaced/);
  assert.equal(await fs.readFile(destination, "utf8"), "replacement after publication");
  assert.deepEqual(await fs.readdir(directory), ["delivered.bin"]);
}));

test("explicit unsupported-link fallback publishes verified bytes without overwriting", () => ownedTest(async ({ directory, destination, request }) => {
  noLinks("ENOTSUP");
  await copyVerifiedArtifact(request);
  assert.deepEqual(await fs.readFile(destination), bytes);
  await assert.rejects(copyVerifiedArtifact(request), { code: "EEXIST" });
  assert.deepEqual(await fs.readFile(destination), bytes);
  assert.deepEqual(await fs.readdir(directory), ["delivered.bin"]);
}));

test("unsupported-link fallback never removes a replacement on a write failure", () => ownedTest(async ({ directory, destination, request }) => {
  noLinks("ENOTSUP");
  const open = fs.open;
  mock.method(fs, "open", async (file, ...args) => {
    const handle = await open(file, ...args);
    if (file === destination) handle.write = async () => {
      await fs.unlink(destination);
      await fs.writeFile(destination, "replacement owned by another writer", { flag: "wx" });
      throw new Error("controlled destination write failure");
    };
    return handle;
  });
  syncBuiltinESMExports();
  await assert.rejects(copyVerifiedArtifact(request), /controlled destination write failure/);
  assert.equal(await fs.readFile(destination, "utf8"), "replacement owned by another writer");
  assert.deepEqual(await fs.readdir(directory), ["delivered.bin"]);
}));

for (const code of ["EPERM", "EACCES", "EXDEV", "EEXIST"]) {
  test(`artifact publication does not weaken ${code} into a fallback`, () => ownedTest(async ({ directory, destination, request }) => {
    noLinks(code);
    await assert.rejects(copyVerifiedArtifact(request), { code });
    await assert.rejects(fs.stat(destination), { code: "ENOENT" });
    assert.deepEqual(await fs.readdir(directory), []);
  }));
}


test("existing artifact destination is rejected before downloading content", () => ownedTest(async ({ destination, request }) => {
  await fs.writeFile(destination, "existing user file", { flag: "wx" });
  let reads = 0;
  await assert.rejects(copyVerifiedArtifact({ ...request, readChunk: async () => { reads++; return bytes; } }), { code: "EEXIST" });
  assert.equal(reads, 0);
  assert.equal(await fs.readFile(destination, "utf8"), "existing user file");
}));
