import {buildCutAgentCliEnv} from "../../local/cli-runtime.mjs";
import {spawn, spawnSync} from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import {
  CUTAGENT_PREPARED_ACTION_CAPABILITY_DIGEST,
  CUTAGENT_PREPARED_ACTION_CONTRACT_DIGEST,
  CUTAGENT_PREPARED_ACTION_KERNEL_DIGEST,
  CUTAGENT_PREPARED_ACTION_MAX_RESULT_BYTES,
} from "../contracts/generated/sdk-prepared-action.js";

const MAX_FRAME_BYTES = CUTAGENT_PREPARED_ACTION_MAX_RESULT_BYTES;
const MACOS_SIGNED_SPAWN_BROKER = String.raw`
ObjC.import("Foundation"); ObjC.import("Security"); ObjC.import("CoreFoundation");
ObjC.bindFunction("posix_spawnattr_init", ["int", ["void **"]]);
ObjC.bindFunction("posix_spawnattr_setflags", ["int", ["void **", "short"]]);
ObjC.bindFunction("posix_spawnattr_setpgroup", ["int", ["void **", "int"]]);
ObjC.bindFunction("posix_spawn", ["int", ["int *", "string", "void *", "void **", "char **", "char **"]]);
ObjC.bindFunction("_NSGetEnviron", ["char ***", []]);
ObjC.bindFunction("kill", ["int", ["int", "int"]]);
ObjC.bindFunction("waitpid", ["int", ["int", "int *", "int"]]);
ObjC.bindFunction("exit", ["void", ["int"]]);
const args = ObjC.unwrap($.NSProcessInfo.processInfo.arguments).map(value => ObjC.unwrap(value));
const separator = args.indexOf("--"); const executable = args[separator + 1]; const mode = args[separator + 2]; const expected = args[separator + 3].toLowerCase();
const attr = Ref(); if ($.posix_spawnattr_init(attr) !== 0) throw new Error("spawn attributes unavailable");
if ($.posix_spawnattr_setflags(attr, 0x0082) !== 0 || $.posix_spawnattr_setpgroup(attr, 0) !== 0) throw new Error("suspended process group unavailable");
const pid = Ref(); const rc = $.posix_spawn(pid, executable, null, attr, [executable, mode, null], $._NSGetEnviron()[0]);
if (rc !== 0) throw new Error("signed child spawn failed");
const childPid = Number(pid[0]);
try {
  const pidValue = Ref("int"); pidValue[0] = childPid; const pidNumber = $.CFNumberCreate(null, 3, pidValue);
  const attributes = $.CFDictionaryCreateMutable(null, 0, null, null); $.CFDictionarySetValue(attributes, $.kSecGuestAttributePid, pidNumber);
  const guest = Ref(); if ($.SecCodeCopyGuestWithAttributes(null, attributes, 0, guest) !== 0) throw new Error("running code unavailable");
  const requirement = Ref(); if ($.SecRequirementCreateWithString($("cdhash H\"" + expected + "\""), 0, requirement) !== 0
    || $.SecCodeCheckValidity(guest[0], 0, requirement[0]) !== 0) throw new Error("running CDHash mismatch");
  $.NSFileHandle.fileHandleWithStandardOutput.writeData($("CUTAGENT_BROKER_READY_V1:" + childPid + "\n").dataUsingEncoding($.NSUTF8StringEncoding));
  if ($.kill(childPid, 19) !== 0) throw new Error("signed child resume failed");
  const status = Ref(); $.waitpid(childPid, status, 0); $.exit(0);
} catch (error) {
  $.kill(childPid, 9); const status = Ref(); $.waitpid(childPid, status, 0); throw error;
}`;
const WINDOWS_SIGNED_SPAWN_BROKER = String.raw`
$ErrorActionPreference='Stop'
$path=$env:CUTAGENT_SIGNED_PREPARED_HOST_PATH
$expectedSha=$env:CUTAGENT_SIGNED_PREPARED_HOST_SHA256
$expectedSize=[long]$env:CUTAGENT_SIGNED_PREPARED_HOST_SIZE
$ownerPid=[uint32]$env:CUTAGENT_SIGNED_PREPARED_OWNER_PID
if (-not $path -or $expectedSha -notmatch '^[a-f0-9]{64}$' -or $expectedSize -lt 1 -or $ownerPid -lt 2) { throw 'signed host binding unavailable' }
$item=Get-Item -LiteralPath $path -Force
if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'signed host reparse point rejected' }
$file=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
try {
  if ($file.Length -ne $expectedSize) { throw 'signed host manifest size rejected' }
  $hasher=[Security.Cryptography.SHA256]::Create()
  try { $actualSha=([BitConverter]::ToString($hasher.ComputeHash($file))).Replace('-','').ToLowerInvariant() } finally { $hasher.Dispose() }
  if ($actualSha -ne $expectedSha) { throw 'signed host manifest digest rejected' }
  $file.Position=0
  $signature=Get-AuthenticodeSignature -LiteralPath $path
  if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Tilkovsk*') { throw 'signed host publisher rejected' }
  $source=@'
using System; using System.Runtime.InteropServices;
public static class CutAgentSignedSpawn {
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct STARTUPINFO { public uint cb; public string lpReserved; public string lpDesktop; public string lpTitle; public uint dwX; public uint dwY; public uint dwXSize; public uint dwYSize; public uint dwXCountChars; public uint dwYCountChars; public uint dwFillAttribute; public uint dwFlags; public short wShowWindow; public short cbReserved2; public IntPtr lpReserved2; public IntPtr hStdInput; public IntPtr hStdOutput; public IntPtr hStdError; }
 [StructLayout(LayoutKind.Sequential)] public struct PROCESS_INFORMATION { public IntPtr hProcess; public IntPtr hThread; public uint dwProcessId; public uint dwThreadId; }
 [StructLayout(LayoutKind.Sequential)] public struct JOBOBJECT_BASIC_LIMIT_INFORMATION { public long PerProcessUserTimeLimit; public long PerJobUserTimeLimit; public uint LimitFlags; public UIntPtr MinimumWorkingSetSize; public UIntPtr MaximumWorkingSetSize; public uint ActiveProcessLimit; public UIntPtr Affinity; public uint PriorityClass; public uint SchedulingClass; }
 [StructLayout(LayoutKind.Sequential)] public struct IO_COUNTERS { public ulong ReadOperationCount; public ulong WriteOperationCount; public ulong OtherOperationCount; public ulong ReadTransferCount; public ulong WriteTransferCount; public ulong OtherTransferCount; }
 [StructLayout(LayoutKind.Sequential)] public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION { public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation; public IO_COUNTERS IoInfo; public UIntPtr ProcessMemoryLimit; public UIntPtr JobMemoryLimit; public UIntPtr PeakProcessMemoryUsed; public UIntPtr PeakJobMemoryUsed; }
 [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcessW(string app, string cmd, IntPtr pa, IntPtr ta, bool inherit, uint flags, IntPtr env, string cwd, ref STARTUPINFO si, out PROCESS_INFORMATION pi);
 [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr CreateJobObjectW(IntPtr attributes,string name); [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int infoClass,ref JOBOBJECT_EXTENDED_LIMIT_INFORMATION info,uint length); [DllImport("kernel32.dll",SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process); [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateJobObject(IntPtr job,uint exitCode); [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint exitCode);
 [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int value); [DllImport("kernel32.dll")] static extern uint ResumeThread(IntPtr thread); [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle,uint ms); [DllImport("kernel32.dll")] static extern uint WaitForMultipleObjects(uint count,IntPtr[] handles,bool waitAll,uint ms); [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr OpenProcess(uint access,bool inherit,uint pid); [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
 public static void Run(string path,uint ownerPid) { IntPtr job=CreateJobObjectW(IntPtr.Zero,null); if(job==IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()); var limit=new JOBOBJECT_EXTENDED_LIMIT_INFORMATION(); limit.BasicLimitInformation.LimitFlags=0x2000; if(!SetInformationJobObject(job,9,ref limit,(uint)Marshal.SizeOf(limit))){CloseHandle(job); throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());} var si=new STARTUPINFO(); si.cb=(uint)Marshal.SizeOf(si); si.dwFlags=0x100; si.hStdInput=GetStdHandle(-10); si.hStdOutput=GetStdHandle(-11); si.hStdError=GetStdHandle(-12); PROCESS_INFORMATION pi; string cmd="\""+path+"\" --cutagent-sdk-prepared-action-host-v1"; if(!CreateProcessW(path,cmd,IntPtr.Zero,IntPtr.Zero,true,0x204,IntPtr.Zero,null,ref si,out pi)){CloseHandle(job); throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());} IntPtr owner=IntPtr.Zero; try { if(!AssignProcessToJobObject(job,pi.hProcess)) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()); owner=OpenProcess(0x00100000,false,ownerPid); if(owner==IntPtr.Zero) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()); if(WaitForSingleObject(owner,0)==0) throw new InvalidOperationException("prepared owner exited before custody"); Console.Out.WriteLine("CUTAGENT_BROKER_READY_V1:"+pi.dwProcessId); Console.Out.Flush(); if(ResumeThread(pi.hThread)==0xffffffff) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()); uint wait=WaitForMultipleObjects(2,new IntPtr[]{job,owner},false,0xffffffff); if(wait==1){TerminateJobObject(job,1); WaitForSingleObject(job,0xffffffff);} else if(wait!=0) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()); } catch { TerminateJobObject(job,1); TerminateProcess(pi.hProcess,1); WaitForSingleObject(pi.hProcess,0xffffffff); WaitForSingleObject(job,0xffffffff); throw; } finally { if(owner!=IntPtr.Zero)CloseHandle(owner); CloseHandle(pi.hThread); CloseHandle(pi.hProcess); CloseHandle(job); } }
}
'@
  $null=Add-Type -TypeDefinition $source -Language CSharp
  [CutAgentSignedSpawn]::Run($path,$ownerPid)
} finally { $file.Dispose() }
`;
const HOST_BOOTSTRAP_TIMEOUT_MS = 15_000;
// A freshly staged standalone runtime can need longer than a normal framed
// exchange while the signed host imports and validates its full action graph.
// Keep bootstrap custody tightly bounded, but give the one cold-start
// initialization handshake its own deadline.
const HOST_INITIALIZATION_TIMEOUT_MS = 60_000;
const HOST_EXCHANGE_TIMEOUT_MS = 30 * 60_000;
const HOST_LONG_RUNNING_EXCHANGE_TIMEOUT_MS = 24 * 60 * 60_000;
const HOST_SHUTDOWN_TIMEOUT_MS = 2_000;
const HOST_EXIT_TIMEOUT_MS = 2_000;

const LONG_RUNNING_ACTIONS = new Set([
  "cutagent.action.auto_edit.multicam",
  "cutagent.action.auto_edit.podcast_edit",
  "cutagent.action.auto_edit.podcast_multicam",
  "cutagent.action.auto_edit.run",
  "cutagent.action.batch.run",
  "cutagent.action.render.export",
  "cutagent.action.render.quick_export",
  "cutagent.action.render.start",
  "cutagent.action.render.wait",
  "cutagent.action.timeline.preview_export",
  "cutagent.action.transcript.create",
]);

export function preparedActionExchangeTimeoutMs({method, actionId = null} = {}) {
  if (["initialize", "shutdown"].includes(method)) return null;
  return method === "execute" && LONG_RUNNING_ACTIONS.has(actionId)
    ? HOST_LONG_RUNNING_EXCHANGE_TIMEOUT_MS
    : HOST_EXCHANGE_TIMEOUT_MS;
}

function callbackFailureDiagnostic({error, method, payload, originalRequest, response}) {
  const message = typeof error?.message === "string" && error.message
    ? error.message.replace(/[^\x20-\x7e\r\n\t]/g, "?").slice(0, 500)
    : "Prepared-action callback failed without a diagnostic message.";
  return Object.freeze({
    phase: `callback.${response.method}`,
    parentMethod: method,
    callbackMethod: response.method,
    actionId: originalRequest?.actionId ?? payload?.request?.actionId ?? null,
    operationId: originalRequest?.operationId ?? payload?.request?.operationId ?? null,
    executionId: originalRequest?.executionId ?? payload?.request?.executionId ?? null,
    errorClass: typeof error?.constructor?.name === "string" ? error.constructor.name : "Error",
    message,
  });
}

function preparedHostPrivateDiagnostic(value, originalRequest, exchange) {
  const bounded = (candidate, maximum, fallback = null) => typeof candidate === "string" && candidate
    ? candidate.replace(/[^\x20-\x7e\r\n\t]/g, "?").slice(0, maximum)
    : fallback;
  const executionFailure = value?.kind === "preparedActionExecutionError"
    && value?.method === "execute"
    && value?.actionId === originalRequest?.actionId
    && value?.operationId === originalRequest?.operationId
    && value?.executionId === originalRequest?.executionId;
  const hostFailure = value?.kind === "preparedActionHostError"
    && value?.requestId === exchange?.requestId
    && value?.method === exchange?.method;
  if (!executionFailure && !hostFailure) return null;
  const phase = bounded(executionFailure ? value.phase : `host.${value.method}`, 200);
  const errorClass = bounded(value.errorClass, 100, "Error");
  const message = bounded(value.message, 500, "Prepared-action runtime failed without a diagnostic message.");
  const trace = bounded(value.trace, 3000);
  if (!phase) return null;
  return Object.freeze({
    phase,
    parentMethod: "execute",
    actionId: originalRequest.actionId,
    operationId: originalRequest.operationId,
    executionId: originalRequest.executionId,
    errorClass,
    message,
    ...(trace ? {trace} : {}),
  });
}

function preparedHostResponseError(response) {
  const failure = response?.error;
  const code = typeof failure?.code === "string" && failure.code
    ? failure.code.replace(/[^\x20-\x7e]/g, "?").slice(0, 120)
    : "RUNTIME_UNAVAILABLE";
  const error = Object.assign(
    new Error(failure?.message ?? "Prepared-action runtime failed."),
    {code},
  );
  const diagnostic = failure?.privateDiagnostic;
  const hostPhase = typeof diagnostic?.hostPhase === "string" && diagnostic.hostPhase
    ? diagnostic.hostPhase.replace(/[^\x20-\x7e]/g, "?").slice(0, 100)
    : null;
  const reason = typeof diagnostic?.reason === "string" && diagnostic.reason
    ? diagnostic.reason.replace(/[^\x20-\x7e\r\n\t]/g, "?").slice(0, 500)
    : null;
  if (hostPhase || reason) {
    Object.defineProperties(error, {
      ...(hostPhase ? {hostPhase: {value: hostPhase}} : {}),
      ...(reason ? {privateReason: {value: reason}} : {}),
    });
  }
  return error;
}

function bounded(promise, milliseconds, onTimeout) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      try { resolve(onTimeout()); } catch (error) { reject(error); }
    }, milliseconds);
    Promise.resolve(promise).then(
      (value) => { clearTimeout(timer); resolve(value); },
      (error) => { clearTimeout(timer); reject(error); },
    );
  });
}

function removeLaunchDirectory(directory) {
  const visit = (current) => {
    try { fs.chmodSync(current, 0o700); } catch { return; }
    try {
      for (const entry of fs.readdirSync(current, {withFileTypes: true})) {
        if (entry.isDirectory() && !entry.isSymbolicLink()) visit(path.join(current, entry.name));
      }
    } catch {}
  };
  visit(directory);
  fs.rmSync(directory, {recursive: true, force: true});
}

function terminateChildTree(child, signal) {
  if (child.exitCode !== null) return;
  child.kill(signal);
}

function waitForBrokerReady(child) {
  return new Promise((resolve, reject) => {
    let buffered = Buffer.alloc(0);
    const finish = (error, pid = null) => {
      child.stdout.off("data", onData);
      child.off("exit", onExit);
      if (error) reject(error); else resolve(pid);
    };
    const onExit = () => finish(new Error("Signed prepared-action broker exited before custody confirmation."));
    const onData = (chunk) => {
      buffered = Buffer.concat([buffered, chunk]);
      if (buffered.length > 256) return finish(new Error("Signed prepared-action broker custody confirmation is invalid."));
      const newline = buffered.indexOf(0x0a);
      if (newline < 0) return;
      const line = buffered.subarray(0, newline).toString("utf8").replace(/\r$/, "");
      const match = /^CUTAGENT_BROKER_READY_V1:([1-9][0-9]*)$/.exec(line);
      const pid = Number.parseInt(match?.[1] ?? "", 10);
      if (!Number.isSafeInteger(pid) || pid <= 1) return finish(new Error("Signed prepared-action broker custody confirmation is invalid."));
      const remainder = buffered.subarray(newline + 1);
      child.stdout.pause();
      child.stdout.off("data", onData);
      child.off("exit", onExit);
      if (remainder.length) child.stdout.unshift(remainder);
      child.stdout.resume();
      resolve(pid);
    };
    child.once("exit", onExit);
    child.stdout.on("data", onData);
  });
}

async function startOwnerWatchdog(targetPid) {
  if (!Number.isSafeInteger(targetPid) || targetPid <= 1) throw new Error("Prepared-action owner watchdog target is invalid.");
  if (process.platform === "win32") return {failClosed() {}, release() {}};
  const watchdog = spawn("/bin/sh", ["-c", `IFS= read -r _ || kill -KILL -- -${targetPid} 2>/dev/null || true`], {
    stdio: ["pipe", "ignore", "ignore"], windowsHide: true,
  });
  await new Promise((resolve, reject) => {
    watchdog.once("spawn", resolve);
    watchdog.once("error", reject);
  });
  let released = false;
  return {
    failClosed() {
      if (released) return;
      released = true;
      watchdog.stdin.destroy();
    },
    release() {
      if (released) return;
      released = true;
      watchdog.stdin.end("released\n");
    },
  };
}

function assertTrustedInstalledRuntime(absolute, resourcesDir) {
  const configuredRoot = path.resolve(resourcesDir ?? "");
  const trustedRoot = fs.realpathSync.native(configuredRoot);
  const real = fs.realpathSync.native(absolute);
  if (real === trustedRoot || !real.startsWith(`${trustedRoot}${path.sep}`)) {
    throw new Error("Prepared-action host escaped the installed application resources.");
  }
  const relative = path.relative(configuredRoot, path.resolve(absolute));
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("Prepared-action resource path is invalid.");
  let current = configuredRoot;
  for (const component of relative.split(path.sep)) {
    current = path.join(current, component);
    if (fs.lstatSync(current).isSymbolicLink()) throw new Error("Prepared-action resource path contains a symbolic link.");
  }
  if (process.platform === "darwin") {
    const signature = spawnSync("/usr/bin/codesign", ["-dv", "--verbose=4", real], {encoding: "utf8"});
    const detail = `${signature.stdout ?? ""}\n${signature.stderr ?? ""}`;
    if (signature.status !== 0 || !detail.includes("TeamIdentifier=P65VQHHXCB")
      || !detail.includes("Identifier=ai.cutagent.cutagent-cli-runtime.cutagent-sdk-session-host")) {
      throw new Error("Prepared-action installed host signature is invalid.");
    }
    const cdhash = detail.match(/\bCDHash=([a-fA-F0-9]+)\b/)?.[1]?.toLowerCase();
    if (!cdhash) throw new Error("Prepared-action installed host CDHash is unavailable.");
    return {path: real, cdhash};
  }
  if (process.platform === "win32") {
    const escaped = real.replaceAll("'", "''");
    const signature = spawnSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", `$s=Get-AuthenticodeSignature -LiteralPath '${escaped}'; Write-Output $s.Status; Write-Output $s.SignerCertificate.Subject`], {encoding: "utf8", windowsHide: true});
    const detail = signature.stdout.trim().split(/\r?\n/);
    if (signature.status !== 0 || detail[0] !== "Valid" || !detail.slice(1).join(" ").includes("Tilkovsk")) throw new Error("Prepared-action installed host signature is invalid.");
    return {path: real, cdhash: null};
  }
  return null;
}

function openVerifiedExecutable(executablePath, bootstrap, {testMutableRoot = false, resourcesDir = null} = {}) {
  const absolute = path.resolve(executablePath);
  const noFollow = fs.constants.O_NOFOLLOW ?? 0;
  const fd = fs.openSync(absolute, fs.constants.O_RDONLY | noFollow);
  let launchDirectory = null;
  try {
    const stat = fs.fstatSync(fd);
    if (!stat.isFile()) throw new Error("Signed prepared-action host is not a regular file.");
    const manifestBytes = fs.readFileSync(path.join(path.dirname(absolute), ".cutagent-runtime-manifest.json"));
    const manifestDigest = crypto.createHash("sha256").update(manifestBytes).digest("hex");
    if (manifestDigest !== bootstrap?.payload?.runtimeManifestDigest) throw new Error("Signed prepared-action host manifest drifted.");
    const manifest = JSON.parse(manifestBytes);
    const entry = manifest?.entries?.find((candidate) => candidate?.path === path.basename(absolute));
    const bytes = fs.readFileSync(fd);
    if (entry?.kind !== "file" || entry.size !== bytes.length
      || entry.sha256 !== crypto.createHash("sha256").update(bytes).digest("hex")) {
      throw new Error("Signed prepared-action host failed manifest custody.");
    }
    const installedExecutable = testMutableRoot ? null : assertTrustedInstalledRuntime(absolute, resourcesDir);
    let launchPath = installedExecutable?.path ?? null;
    if (!installedExecutable) {
      launchDirectory = fs.mkdtempSync(path.join(path.dirname(absolute), ".cutagent-signed-host-"));
      launchPath = path.join(launchDirectory, path.basename(absolute));
      fs.linkSync(absolute, launchPath);
      const launchStat = fs.lstatSync(launchPath);
      if (launchStat.dev !== stat.dev || launchStat.ino !== stat.ino || launchStat.isSymbolicLink()) {
        throw new Error("Signed prepared-action host launch custody changed.");
      }
    }
    const runtimeName = process.platform === "win32" ? "cutagent-runtime.exe" : "cutagent-runtime";
    const runtimePath = path.join(path.dirname(absolute), runtimeName);
    const runtimeEntry = manifest?.entries?.find((candidate) => candidate?.path === runtimeName);
    const runtimeFd = fs.openSync(runtimePath, fs.constants.O_RDONLY | noFollow);
    try {
      const runtimeStat = fs.fstatSync(runtimeFd);
      const runtimeBytes = fs.readFileSync(runtimeFd);
      if (!runtimeStat.isFile() || runtimeEntry?.kind !== "file" || runtimeEntry.size !== runtimeBytes.length
        || runtimeEntry.sha256 !== crypto.createHash("sha256").update(runtimeBytes).digest("hex")) {
        throw new Error("Proprietary prepared-action runtime failed manifest custody.");
      }
      if (launchDirectory) {
        const launchRuntime = path.join(launchDirectory, runtimeName);
        fs.linkSync(runtimePath, launchRuntime);
        const linkedRuntime = fs.lstatSync(launchRuntime);
        if (linkedRuntime.dev !== runtimeStat.dev || linkedRuntime.ino !== runtimeStat.ino || linkedRuntime.isSymbolicLink()) {
          throw new Error("Proprietary prepared-action runtime launch custody changed.");
        }
      }
    } finally { fs.closeSync(runtimeFd); }
    if (launchDirectory) {
      fs.writeFileSync(path.join(launchDirectory, ".cutagent-runtime-manifest.json"), manifestBytes, {mode: 0o400});
      fs.chmodSync(launchDirectory, 0o700);
    }
    return {
      fd,
      executable: launchPath,
      installedCdHash: installedExecutable?.cdhash ?? null,
      expectedSha256: entry.sha256,
      expectedSize: entry.size,
      cleanup() {
        if (launchDirectory) removeLaunchDirectory(launchDirectory);
      },
    };
  } catch (error) {
    fs.closeSync(fd);
    if (launchDirectory) {
      removeLaunchDirectory(launchDirectory);
    }
    throw error;
  }
}

class FrameChannel {
  constructor(child, failureDetail = () => "") {
    this.child = child;
    this.failureDetail = failureDetail;
    this.buffer = Buffer.alloc(0);
    this.waiters = [];
    this.failure = null;
    this.pendingHostFailure = null;
    this.failureObserved = new Promise((resolve) => { this.resolveFailure = resolve; });
    child.stdout.on("data", (chunk) => { this.buffer = Buffer.concat([this.buffer, chunk]); this.#drain(); });
    child.stdin.on("error", () => this.#scheduleHostFailure("Signed prepared-action host disconnected."));
    child.once("error", () => this.#fail(this.#hostFailure("Signed prepared-action host failed.")));
    child.once("close", () => {
      if (this.pendingHostFailure) clearTimeout(this.pendingHostFailure);
      this.pendingHostFailure = null;
      this.#fail(this.#hostFailure("Signed prepared-action host disconnected."));
    });
  }

  #hostFailure(message) {
    const detail = this.failureDetail();
    return new Error(detail ? `${message} Private host diagnostic: ${detail}` : message);
  }

  #fail(error) {
    if (this.failure) return;
    this.failure = error;
    this.resolveFailure(error);
    for (const waiter of this.waiters.splice(0)) waiter.reject(error);
  }

  #scheduleHostFailure(message) {
    if (this.failure || this.pendingHostFailure) return;
    // A write-side EPIPE can arrive before the child's stderr and close events.
    // `close` is emitted only after stdio has drained, so prefer it for the
    // diagnostic. The short fallback still fails a host that closes stdin but
    // remains alive without leaving bootstrap blocked until the outer timeout.
    this.pendingHostFailure = setTimeout(() => {
      this.pendingHostFailure = null;
      this.#fail(this.#hostFailure(message));
    }, 100);
    this.pendingHostFailure.unref?.();
  }

  #drain() {
    while (this.waiters.length && this.buffer.length >= 4) {
      const length = this.buffer.readUInt32BE(0);
      if (length < 2 || length > MAX_FRAME_BYTES) return this.#fail(new Error("Signed prepared-action host returned an invalid frame."));
      if (this.buffer.length < length + 4) return;
      const bytes = this.buffer.subarray(4, length + 4);
      this.buffer = this.buffer.subarray(length + 4);
      let value;
      try { value = JSON.parse(bytes.toString("utf8")); } catch { return this.#fail(new Error("Signed prepared-action host returned invalid JSON.")); }
      this.waiters.shift().resolve(value);
    }
  }

  read() {
    if (this.failure) return Promise.reject(this.failure);
    return new Promise((resolve, reject) => { this.waiters.push({resolve, reject}); this.#drain(); });
  }

  async write(value) {
    const bytes = Buffer.from(JSON.stringify(value), "utf8");
    if (bytes.length < 2 || bytes.length > MAX_FRAME_BYTES) throw new Error("Signed prepared-action request exceeded its bound.");
    const header = Buffer.alloc(4); header.writeUInt32BE(bytes.length);
    await new Promise((resolve, reject) => {
      this.child.stdin.write(Buffer.concat([header, bytes]), (error) => {
        if (error) {
          this.#scheduleHostFailure("Signed prepared-action host disconnected.");
          this.failureObserved.then(reject);
        }
        else resolve();
      });
    });
  }
}

/** Persistent private client for the signed Rust host; callers cannot supply a command or lowering. */
export async function createSdkPreparedActionRuntimeClient({
  executablePath,
  bootstrap,
  initialization,
  redeemAuthorization,
  assertProtectedState,
  inspectPreparedActionTimeline = null,
  resolveLiveTargets = null,
  originalRequest = null,
  spawnProcess = spawn,
  resourcesDir = process.env.CUTAGENT_APP_RESOURCES_DIR,
  observeSpawnedChildForTest = null,
  onCallbackError = null,
  privateEvaluatorDiagnostics = false,
  runtimeEnv = {},
  exchangeTimeoutFor = preparedActionExchangeTimeoutMs,
} = {}) {
  if (typeof redeemAuthorization !== "function" || typeof assertProtectedState !== "function") {
    throw new TypeError("Prepared-action runtime callbacks are required.");
  }
  if (onCallbackError !== null && typeof onCallbackError !== "function") {
    throw new TypeError("Prepared-action callback diagnostic sink is invalid.");
  }
  if (typeof exchangeTimeoutFor !== "function") {
    throw new TypeError("Prepared-action exchange deadline resolver is invalid.");
  }
  const child = spawnProcess(executablePath, [], {
    stdio: ["pipe", "pipe", "pipe"], windowsHide: true, detached: process.platform !== "win32",
    env: buildCutAgentCliEnv({args: [], extraEnv: runtimeEnv}),
  });
  const productionMacBroker = false;
  const productionWindowsBroker = false;
  let ownerWatchdog = null;
  const cleanup = () => {};
  let hostDiagnostic = Buffer.alloc(0);
  let privateDiagnosticLines = Buffer.alloc(0);
  let privateDiagnosticRequest = null;
  child.stderr?.on("data", (chunk) => {
    if (hostDiagnostic.length < 8 * 1024) {
      hostDiagnostic = Buffer.concat([hostDiagnostic, chunk]).subarray(0, 8 * 1024);
    }
    privateDiagnosticLines = Buffer.concat([privateDiagnosticLines, chunk]).subarray(-16 * 1024);
    for (;;) {
      const newline = privateDiagnosticLines.indexOf(0x0a);
      if (newline < 0) break;
      const line = privateDiagnosticLines.subarray(0, newline).toString("utf8");
      privateDiagnosticLines = privateDiagnosticLines.subarray(newline + 1);
      try {
        const diagnostic = privateEvaluatorDiagnostics
          ? preparedHostPrivateDiagnostic(
            JSON.parse(line), originalRequest, privateDiagnosticRequest,
          )
          : null;
        if (diagnostic) onCallbackError?.(diagnostic);
      } catch {
        // Private diagnostics cannot alter the fail-closed runtime exchange.
      }
    }
  });
  const privateHostDiagnostic = () => hostDiagnostic.toString("utf8")
    .replace(/[^\x20-\x7e\r\n\t]/g, "?")
    .trim()
    .slice(-2 * 1024);
  const brokered = productionMacBroker || productionWindowsBroker;
  let ownedPid;
  try {
    ownedPid = brokered
      ? await bounded(waitForBrokerReady(child), HOST_BOOTSTRAP_TIMEOUT_MS, () => {
        terminateChildTree(child, "SIGKILL");
        throw new Error("Prepared-action broker custody confirmation timed out.");
      })
      : child.pid;
    ownerWatchdog = await startOwnerWatchdog(ownedPid);
    observeSpawnedChildForTest?.(ownedPid);
  } catch (error) {
    terminateChildTree(child, "SIGKILL");
    cleanup();
    throw error;
  }
  child.once("exit", () => {
    ownerWatchdog?.failClosed();
    cleanup();
  });
  const channel = new FrameChannel(child, privateHostDiagnostic);
  let requestSequence = 0;
  let inFlight = false;
  let closing = false;
  let closePromise = null;
  let runtimeFailure = null;
  const receiptRequests = new Map();

  async function exchange(method, payload) {
    if (runtimeFailure) throw runtimeFailure;
    if (closing && method !== "shutdown") throw new Error("Prepared-action runtime is closing.");
    if (inFlight) throw new Error("Prepared-action runtime permits one request at a time.");
    inFlight = true;
    const requestId = `prepared_host_request_${++requestSequence}`;
    privateDiagnosticRequest = {requestId, method};
    try {
      const request = method === "prepare"
        ? payload?.request
        : receiptRequests.get(payload?.receipt) ?? originalRequest;
      const timeoutMs = exchangeTimeoutFor({method, actionId: request?.actionId ?? payload?.actionId ?? null});
      if (timeoutMs !== null && (!Number.isInteger(timeoutMs) || timeoutMs < 1)) {
        throw new TypeError("Prepared-action exchange deadline is invalid.");
      }
      const pending = (async () => {
        await channel.write({requestId, method, payload});
        for (;;) {
          const response = await channel.read();
          if (response?.kind === "callback") {
            if (response.parentRequestId !== requestId || !Number.isSafeInteger(response.sequence)) throw new Error("Prepared-action callback correlation failed.");
            try {
              let value;
              if (response.method === "redeemAuthorization") value = await redeemAuthorization(response.payload);
              else if (response.method === "assertProtectedState") value = await assertProtectedState(response.payload);
              else if (response.method === "inspectPreparedActionTimeline" && typeof inspectPreparedActionTimeline === "function") value = await inspectPreparedActionTimeline(response.payload);
              else if (response.method === "resolveLiveTargets" && typeof resolveLiveTargets === "function") {
                const request = method === "prepare" ? payload?.request : receiptRequests.get(payload?.receipt) ?? originalRequest;
                if (!request) throw new Error("Prepared-action live target callback lost its exact original request.");
                value = await resolveLiveTargets(structuredClone(response.payload), {
                  parentMethod: method,
                  parentPayload: structuredClone(payload),
                  originalRequest: structuredClone(request),
                });
              }
              else throw new Error("Prepared-action callback method is invalid.");
              await channel.write({kind: "callbackResult", parentRequestId: requestId, callbackId: response.callbackId, sequence: response.sequence, ok: true, value});
            } catch (error) {
              try {
                onCallbackError?.(callbackFailureDiagnostic({error, method, payload, originalRequest, response}));
              } catch {
                // Private diagnostics must never change the fail-closed host contract.
              }
              const allowedCallbackCodes = response.method === "resolveLiveTargets"
                ? new Set(["STALE_REVISION", "CAPABILITY_NEGOTIATION_FAILED"])
                : response.method === "inspectPreparedActionTimeline"
                  ? new Set(["STALE_REVISION"])
                  : new Set();
              const callbackCode = allowedCallbackCodes.has(error?.code)
                ? error.code
                : "RUNTIME_UNAVAILABLE";
              await channel.write({
                kind: "callbackResult", parentRequestId: requestId, callbackId: response.callbackId,
                sequence: response.sequence, ok: false, error: {code: callbackCode},
              });
            }
            continue;
          }
          if (response?.kind !== "response" || response.requestId !== requestId) throw new Error("Prepared-action response correlation failed.");
          if (response.ok !== true) throw preparedHostResponseError(response);
          if (method === "prepare" && typeof response.value?.receipt === "string") {
            receiptRequests.set(response.value.receipt, structuredClone(payload.request));
          }
          return response.value;
        }
      })();
      if (timeoutMs === null) return await pending;
      return await bounded(pending, timeoutMs, () => {
        const error = Object.assign(
          new Error(`Prepared-action ${method} exceeded its execution deadline.`),
          {
            code: "PREPARED_ACTION_DEADLINE_EXCEEDED",
            phase: method,
            possibleMutation: method === "execute",
          },
        );
        runtimeFailure = error;
        terminateChildTree(child, "SIGKILL");
        ownerWatchdog?.failClosed();
        throw error;
      });
    } finally {
      if (["execute", "revoke"].includes(method) && typeof payload?.receipt === "string") receiptRequests.delete(payload.receipt);
      inFlight = false;
    }
  }

  let advertisement;
  try {
    advertisement = await bounded(exchange("initialize", initialization), HOST_INITIALIZATION_TIMEOUT_MS, () => {
      terminateChildTree(child, "SIGKILL");
      throw new Error("Prepared-action initialization timed out.");
    });
  } catch (error) {
    terminateChildTree(child, "SIGKILL");
    cleanup();
    throw error;
  }
  if (advertisement?.contractDigest !== CUTAGENT_PREPARED_ACTION_CONTRACT_DIGEST
    || advertisement?.capabilityDigest !== CUTAGENT_PREPARED_ACTION_CAPABILITY_DIGEST
    || advertisement?.protocolDigest !== CUTAGENT_PREPARED_ACTION_KERNEL_DIGEST
    || !Array.isArray(advertisement?.advertisedActionIds)) {
    terminateChildTree(child, "SIGKILL");
    throw new Error("Prepared-action registry advertisement drifted.");
  }
  const advertised = new Set(advertisement.advertisedActionIds);
  return Object.freeze({
    advertisedActionIds: Object.freeze([...advertised].sort()),
    hasAction(actionId) { return advertised.has(actionId); },
    prepare(payload) { return exchange("prepare", payload); },
    acceptPolicy(payload) { return exchange("acceptPolicy", payload); },
    admit(payload) { return exchange("admit", payload); },
    execute(payload) { return exchange("execute", payload); },
    recoverTerminal(payload) { return exchange("recoverTerminal", payload); },
    revoke(payload) { return exchange("revoke", payload); },
    close() {
      closePromise ??= (async () => {
        closing = true;
        if (child.exitCode !== null) return;
        try {
          if (!inFlight && !runtimeFailure) await bounded(exchange("shutdown", {}), HOST_SHUTDOWN_TIMEOUT_MS, () => null);
        } catch {
        } finally {
          child.stdin.end();
        }
        if (child.exitCode === null) terminateChildTree(child, "SIGTERM");
        if (child.exitCode === null) await bounded(
          new Promise((resolve) => child.once("exit", resolve)),
          HOST_EXIT_TIMEOUT_MS,
          () => {
            terminateChildTree(child, "SIGKILL");
          },
        );
        ownerWatchdog?.release();
        cleanup();
      })();
      return closePromise;
    },
  });
}
