import assert from "node:assert/strict";
import {mkdtemp, mkdir, readFile, writeFile, access, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";
import {spawnSync} from "node:child_process";
import {createHash} from "node:crypto";
import test from "node:test";

const root = resolve(import.meta.dirname, "..");
const entry = join(root, "bin", "cutagent.mjs");

test("setup preserves an existing canonical launcher and returns a structured collision", async () => {
  if (process.platform === "win32") return;
  const directory = await mkdtemp(join(tmpdir(), "cutagent-sdk-collision-"));
  const state = join(directory, "state");
  const bin = join(directory, "bin");
  const launcher = join(bin, "cutagent");
  await mkdir(bin, {recursive: true});
  await writeFile(launcher, "valuable existing launcher\n", {mode: 0o755});

  const result = spawnSync(process.execPath, [entry, "setup", "--skip-python", "--state-dir", state, "--bin-dir", bin, "--json"], {
    cwd: root,
    encoding: "utf8",
  });
  assert.equal(result.status, 1, result.stderr);
  const envelope = JSON.parse(result.stdout);
  assert.equal(envelope.ok, false);
  assert.equal(envelope.error.code, "CUTAGENT_COMMAND_COLLISION");
  assert.equal(await readFile(launcher, "utf8"), "valuable existing launcher\n");
  await assert.rejects(access(join(state, "versions", "3.0.0")));
});

test("the installed command binds exact local command identity without forwarding account secrets", async () => {
  if (process.platform === "win32") return;
  const directory = await mkdtemp(join(tmpdir(), "cutagent-sdk-forward-"));
  const state = join(directory, "state");
  const installed = join(directory, "installed");
  const fakePython = join(directory, "fake-python");
  await mkdir(join(installed, "native"), {recursive: true});
  await mkdir(state, {recursive: true});
  await writeFile(join(state, "installation.json"), `${JSON.stringify({formatVersion: 1, version: "3.0.0", installRoot: installed, launcher: join(directory, "cutagent"), defaultTransport: "embedded_free"})}\n`);
  await writeFile(fakePython, `#!/usr/bin/env node\nprocess.stdout.write(JSON.stringify({args:process.argv.slice(2),env:{transport:process.env.CUTAGENT_RESOLVE_TRANSPORT,commandDigest:process.env.DAVINCI_RESOLVE_SDK_COMMAND_SHA256,parent:process.env.DAVINCI_RESOLVE_SDK_PARENT_PID,accountSecret:process.env.CUTAGENT_CLI_AUTH_TOKEN,brokerSecret:process.env.CUTAGENT_CLI_BROKER_TOKEN}}));\n`, {mode: 0o755});
  const args = ["--json", "project", "create", "Owned test project", "--state-dir", state, "--python", fakePython];
  const result = spawnSync(process.execPath, [entry, ...args], {
    cwd: root,
    encoding: "utf8",
    env: {...process.env, CUTAGENT_CLI_AUTH_TOKEN: "must-not-forward", CUTAGENT_CLI_BROKER_TOKEN: "must-not-forward"},
  });
  assert.equal(result.status, 0, result.stderr);
  const observed = JSON.parse(result.stdout);
  const digest = createHash("sha256").update(JSON.stringify(args)).digest("hex");
  assert.equal(observed.env.transport, "embedded_free");
  assert.equal(observed.env.commandDigest, digest);
  assert.equal(observed.env.parent, String(result.pid));
  assert.equal(observed.env.accountSecret, undefined);
  assert.equal(observed.env.brokerSecret, undefined);
});

test("Free setup reports and retains the embedded DaVinci Resolve connection", async (t) => {
  if (process.platform === "win32") return;
  const directory = await mkdtemp(join(tmpdir(), "cutagent-free-setup-"));
  t.after(() => rm(directory, {recursive: true, force: true}));
  const state = join(directory, "state");
  const bin = join(directory, "bin");
  const result = spawnSync(process.execPath, [entry, "setup", "--skip-python", "--free", "--state-dir", state, "--bin-dir", bin, "--json"], {
    cwd: root,
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  const envelope = JSON.parse(result.stdout);
  assert.equal(envelope.ok, true);
  assert.equal(envelope.data.defaultTransport, "embedded_free");
  assert.match(envelope.data.message, /--transport embedded_free/);
  const installation = JSON.parse(await readFile(join(state, "installation.json"), "utf8"));
  assert.equal(installation.defaultTransport, "embedded_free");
});
