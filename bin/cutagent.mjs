#!/usr/bin/env node

// CUTAGENT_STANDALONE_LAUNCHER_V1
import {createHash} from "node:crypto";
import {constants, cpSync, existsSync, lstatSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync} from "node:fs";
import {homedir} from "node:os";
import {dirname, join, resolve} from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";
import {spawnSync} from "node:child_process";

const packageRoot = realpathSync(resolve(dirname(fileURLToPath(import.meta.url)), ".."));
const manifest = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8"));
const args = process.argv.slice(2);

function option(name) {
  const index = args.indexOf(name);
  return index === -1 ? null : args[index + 1] ?? null;
}

function stateRoot() {
  return resolve(option("--state-dir") ?? process.env.CUTAGENT_SDK_STATE_DIR ?? join(homedir(), ".local", "share", "cutagent-sdk"));
}

function jsonMode() {
  return args.includes("--json") || args.includes("-j");
}

function emit(ok, data = null, error = null) {
  const envelope = {ok, data, error, meta: {distribution: "standalone_local", version: manifest.version}};
  if (jsonMode()) process.stdout.write(`${JSON.stringify(envelope)}\n`);
  else if (ok) process.stdout.write(`${data?.message ?? "Done."}\n`);
  else process.stderr.write(`${error.code}: ${error.message}\n${error.suggested_fix ?? ""}\n`);
}

function fail(code, message, suggestedFix, details = undefined) {
  emit(false, null, {code, message, suggested_fix: suggestedFix, ...(details ? {details} : {})});
  process.exitCode = 1;
}

function run(command, commandArgs, options = {}) {
  const result = spawnSync(command, commandArgs, {stdio: "inherit", ...options});
  if (result.error) throw result.error;
  return result.status ?? 1;
}

function installRoot(root = stateRoot()) {
  return join(root, "versions", manifest.version);
}

function launcherPath(root = stateRoot()) {
  return resolve(option("--bin-dir") ?? join(homedir(), ".local", "bin"), process.platform === "win32" ? "cutagent.cmd" : "cutagent");
}

function managedLauncher(path) {
  if (!existsSync(path)) return false;
  try {
    const text = readFileSync(path, "utf8");
    return text.includes("CUTAGENT_STANDALONE_LAUNCHER_V1");
  } catch {
    return false;
  }
}

function copyCandidate(destination) {
  const temporary = `${destination}.staging-${process.pid}`;
  rmSync(temporary, {recursive: true, force: true});
  mkdirSync(dirname(destination), {recursive: true, mode: 0o700});
  cpSync(packageRoot, temporary, {
    recursive: true,
    dereference: false,
    filter(source) {
      const relative = source.slice(packageRoot.length).replace(/^\//, "");
      return !relative.startsWith(".git") && !relative.startsWith("node_modules") && !relative.includes("/.venv");
    },
  });
  rmSync(destination, {recursive: true, force: true});
  mkdirSync(dirname(destination), {recursive: true, mode: 0o700});
  const rename = spawnSync(process.execPath, ["-e", "require('node:fs').renameSync(process.argv[1],process.argv[2])", temporary, destination]);
  if (rename.status !== 0) throw new Error("CutAgent SDK files could not be prepared.");
}

function writeLauncher(path, installedRoot) {
  mkdirSync(dirname(path), {recursive: true, mode: 0o700});
  if (existsSync(path) && !managedLauncher(path)) {
    throw Object.assign(new Error("Another installation already provides the cutagent command."), {code: "CUTAGENT_COMMAND_COLLISION"});
  }
  const nodeEntry = join(installedRoot, "bin", "cutagent.mjs");
  if (process.platform === "win32") {
    writeFileSync(path, `@echo off\r\nrem CUTAGENT_STANDALONE_LAUNCHER_V1\r\n"${process.execPath}" "${nodeEntry}" %*\r\n`, "utf8");
  } else {
    writeFileSync(path, `#!/bin/sh\n# CUTAGENT_STANDALONE_LAUNCHER_V1\nexec "${process.execPath}" "${nodeEntry}" "$@"\n`, {encoding: "utf8", mode: 0o755});
  }
}

function setup() {
  if (process.platform === "win32") {
    fail("PLATFORM_NOT_QUALIFIED", "CutAgent SDK setup for Windows is not available yet.", "Windows support is still being tested.");
    return;
  }
  const root = stateRoot();
  const destination = installRoot(root);
  const commandPath = launcherPath(root);
  try {
    if (existsSync(commandPath) && !managedLauncher(commandPath)) {
      throw Object.assign(new Error("Another installation already provides the cutagent command."), {code: "CUTAGENT_COMMAND_COLLISION"});
    }
    copyCandidate(destination);
    const npm = process.platform === "win32" ? "npm.cmd" : "npm";
    const childStdio = jsonMode() ? "ignore" : "inherit";
    const npmStatus = run(npm, ["install", "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund"], {cwd: destination, stdio: childStdio});
    if (npmStatus !== 0) throw new Error("The required Node.js packages could not be installed.");
    const python = option("--python") ?? "python3.12";
    const venv = join(destination, ".venv");
    if (!args.includes("--skip-python")) {
      if (run(python, ["-m", "venv", venv], {stdio: childStdio}) !== 0) throw new Error("CutAgent SDK could not prepare Python 3.12.");
      const pythonBin = join(venv, "bin", "python");
      if (run(pythonBin, ["-m", "pip", "install", "-r", join(destination, "native", "requirements.lock.txt")], {stdio: childStdio}) !== 0) {
        throw new Error("The required Python packages could not be installed.");
      }
      if (args.includes("--free") && run(pythonBin, [join(destination, "native", "free_broker.py"), "install"], {stdio: childStdio}) !== 0) {
        throw new Error("The DaVinci Resolve Free script could not be installed.");
      }
    }
    writeLauncher(commandPath, destination);
    mkdirSync(root, {recursive: true, mode: 0o700});
    const defaultTransport = args.includes("--free") ? "embedded_free" : "studio_external";
    writeFileSync(join(root, "installation.json"), `${JSON.stringify({formatVersion: 1, version: manifest.version, installRoot: destination, launcher: commandPath, defaultTransport}, null, 2)}\n`, {encoding: "utf8", mode: 0o600});
    emit(true, {message: `CutAgent SDK ${manifest.version} is ready. Connect it to DaVinci Resolve with: ${commandPath} runtime start --transport ${defaultTransport}`, installRoot: destination, launcher: commandPath, defaultTransport});
  } catch (error) {
    fail(error.code ?? "SETUP_FAILED", error.message, error.code === "CUTAGENT_COMMAND_COLLISION"
      ? "Keep the existing command, or choose another folder with --bin-dir. The existing command was not changed."
      : "Check Node.js 22 or 24, Python 3.12, your internet connection, and folder permissions, then try again.");
  }
}

function loadInstallation() {
  const path = join(stateRoot(), "installation.json");
  if (!existsSync(path)) return null;
  try {
    const value = JSON.parse(readFileSync(path, "utf8"));
    if (value?.formatVersion !== 1 || typeof value.installRoot !== "string") return null;
    return value;
  } catch {
    return null;
  }
}

async function startRuntime() {
  const installation = loadInstallation();
  const root = installation?.installRoot ?? packageRoot;
  const transport = option("--transport") ?? installation?.defaultTransport ?? "studio_external";
  if (!["studio_external", "embedded_free"].includes(transport)) {
    fail("INVALID_TRANSPORT", "Choose the connection for your DaVinci Resolve edition.", "Use --transport studio_external for Studio or --transport embedded_free for Free.");
    return;
  }
  const runtimeState = resolve(option("--runtime-state") ?? join(stateRoot(), "runtime-state"));
  mkdirSync(runtimeState, {recursive: true, mode: 0o700});
  const {startNativeLocalRuntime} = await import(pathToFileURL(join(root, "runtime", "index.mjs")));
  const runtime = await startNativeLocalRuntime({stateDirectory: runtimeState, transport});
  emit(true, {message: "CutAgent SDK is connected to DaVinci Resolve.", discoveryFile: runtime.discoveryFile, transport});
  let closing = false;
  const close = async () => {
    if (closing) return;
    closing = true;
    await runtime.close();
  };
  process.on("SIGINT", close);
  process.on("SIGTERM", close);
}

function status() {
  const installation = loadInstallation();
  const discovery = join(stateRoot(), "runtime-state", "cutagent-sdk-discovery-v1.json");
  emit(true, {message: installation ? `CutAgent SDK ${installation.version} is installed.` : "CutAgent SDK setup has not run.", installed: Boolean(installation), installation, runtimeDiscoveryPresent: existsSync(discovery)});
}

function uninstall() {
  const installation = loadInstallation();
  const root = stateRoot();
  if (!installation) {
    emit(true, {message: "No managed CutAgent SDK installation was found.", removed: []});
    return;
  }
  const removed = [];
  if (managedLauncher(installation.launcher)) {
    rmSync(installation.launcher, {force: true});
    removed.push(installation.launcher);
  }
  if (installation.installRoot.startsWith(`${resolve(root)}${process.platform === "win32" ? "\\" : "/"}`)) {
    rmSync(installation.installRoot, {recursive: true, force: true});
    removed.push(installation.installRoot);
  }
  rmSync(join(root, "installation.json"), {force: true});
  emit(true, {message: "CutAgent SDK was removed. Project recovery data was kept.", removed});
}

function forwardToNative() {
  const installation = loadInstallation();
  const root = installation?.installRoot ?? packageRoot;
  const python = existsSync(join(root, ".venv", "bin", "python")) ? join(root, ".venv", "bin", "python") : option("--python") ?? "python3.12";
  const digest = createHash("sha256").update(JSON.stringify(args)).digest("hex");
  const forwardedKeys = ["PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "WINDIR", "TMPDIR", "TEMP", "LANG", "LC_ALL", "RESOLVE_SCRIPT_API", "RESOLVE_SCRIPT_LIB", "DYLD_LIBRARY_PATH", "DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_PATH", "DAVINCI_RESOLVE_SDK_EMBEDDED_PORT"];
  const nativeEnv = Object.fromEntries(forwardedKeys.filter((key) => process.env[key] !== undefined).map((key) => [key, process.env[key]]));
  process.exitCode = run(python, [join(root, "native", "cutagent"), ...args], {env: {
    ...nativeEnv,
    CUTAGENT_RESOLVE_TRANSPORT: installation?.defaultTransport ?? "studio_external",
    DAVINCI_RESOLVE_SDK_COMMAND_SHA256: digest,
    DAVINCI_RESOLVE_SDK_PARENT_PID: String(process.pid),
  }});
}

const command = args[0];
if (command === "--version" || command === "-V" || command === "version") process.stdout.write(`${manifest.version}\n`);
else if (command === "setup") setup();
else if (command === "status") status();
else if (command === "uninstall") uninstall();
else if (command === "update") emit(true, {message: "Install the reviewed newer package with npm, then run `cutagent setup` again. Automatic download is intentionally disabled."});
else if (command === "runtime" && args[1] === "start") await startRuntime();
else if (!command || command === "help" || command === "--help" || command === "-h") process.stdout.write(`CutAgent SDK ${manifest.version}\n\nCommands:\n  setup [--python python3.12] [--free] [--bin-dir DIR]\n  status [--json]\n  runtime start --transport studio_external|embedded_free\n  update\n  uninstall\n  <CutAgent CLI command>\n`);
else forwardToNative();
