import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const MANAGED_PROCESS_TERM_WAIT_MS = 750;
const PORT_RELEASE_WAIT_MS = 2500;

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function listeningPidsForPort(port, {
  platform = process.platform,
  execFileFn = execFileAsync,
  currentPid = process.pid,
} = {}) {
  if (platform !== "darwin") {
    return [];
  }
  try {
    const { stdout } = await execFileFn("lsof", [
      "-nP",
      "-t",
      `-iTCP:${port}`,
      "-sTCP:LISTEN",
    ], {
      encoding: "utf8",
      timeout: 1500,
      shell: false,
    });
    return stdout
      .split(/\s+/)
      .map((value) => Number.parseInt(value, 10))
      .filter((pid) => Number.isInteger(pid) && pid > 0 && pid !== currentPid);
  } catch {
    return [];
  }
}

export async function inspectProcessIdentity(pid, {
  platform = process.platform,
  execFileFn = execFileAsync,
} = {}) {
  if (platform !== "darwin" || !Number.isInteger(pid) || pid <= 0) {
    return null;
  }
  try {
    const { stdout } = await execFileFn("/bin/ps", [
      "-p",
      String(pid),
      "-o",
      "ppid=",
      "-o",
      "command=",
    ], {
      encoding: "utf8",
      timeout: 1500,
      shell: false,
      maxBuffer: 64 * 1024,
    });
    const match = String(stdout ?? "").trim().match(/^(\d+)\s+(.+)$/s);
    if (!match) {
      return null;
    }
    const parentPid = Number.parseInt(match[1], 10);
    return Number.isInteger(parentPid) && parentPid >= 0
      ? { pid, parentPid, command: match[2] }
      : null;
  } catch {
    return null;
  }
}

export async function terminateWindowsProcessTree(pid, {
  env = process.env,
  platform = process.platform,
  execFileFn = execFileAsync,
} = {}) {
  if (platform !== "win32" || !Number.isInteger(pid) || pid <= 0) {
    return false;
  }
  const systemRoot = typeof env.SystemRoot === "string" && env.SystemRoot.trim()
    ? env.SystemRoot.trim()
    : typeof env.WINDIR === "string" && env.WINDIR.trim()
      ? env.WINDIR.trim()
      : "";
  if (!systemRoot || !path.win32.isAbsolute(systemRoot)) {
    return false;
  }
  try {
    await execFileFn(path.win32.join(systemRoot, "System32", "taskkill.exe"), [
      "/PID",
      String(pid),
      "/T",
      "/F",
    ], {
      encoding: "utf8",
      timeout: 2500,
      windowsHide: true,
      shell: false,
      maxBuffer: 64 * 1024,
    });
    return true;
  } catch {
    return false;
  }
}

export function isManagedEmbeddedRuntimeProcess(identity, {
  env = process.env,
  allowedParentPids = [1],
} = {}) {
  if (!identity || !allowedParentPids.includes(identity.parentPid)) {
    return false;
  }
  const resourceDir = typeof env.CUTAGENT_APP_RESOURCES_DIR === "string"
    ? env.CUTAGENT_APP_RESOURCES_DIR.trim()
    : "";
  if (!resourceDir || !path.isAbsolute(resourceDir)) {
    return false;
  }
  const runtimeRoot = path.join(path.resolve(resourceDir), "binaries", "cutagent-cli-runtime");
  const runtimeExecutables = [
    path.join(runtimeRoot, "bin", "python3"),
    path.join(runtimeRoot, "bin", "python3.14"),
    path.join(runtimeRoot, "cutagent-runtime"),
  ];
  const command = typeof identity.command === "string" ? identity.command : "";
  const exactRuntime = runtimeExecutables.some((candidate) => (
    command === candidate || command.startsWith(`${candidate} `)
  ));
  return exactRuntime && /(?:^|\s)embedded\s+start-server(?:\s|$)/.test(command);
}

export async function managedEmbeddedRuntimePidsForPort(port, {
  env = process.env,
  allowedParentPids = [1],
  listeningPidsFn = listeningPidsForPort,
  inspectProcessFn = inspectProcessIdentity,
} = {}) {
  const pids = await listeningPidsFn(port);
  const identities = await Promise.all(pids.map((pid) => inspectProcessFn(pid)));
  return identities
    .filter((identity) => isManagedEmbeddedRuntimeProcess(identity, {
      env,
      allowedParentPids,
    }))
    .map((identity) => identity.pid);
}

export async function waitForPortRelease(port, {
  timeoutMs = PORT_RELEASE_WAIT_MS,
  listeningPidsFn = listeningPidsForPort,
  delayFn = delay,
} = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const pids = await listeningPidsFn(port);
    if (pids.length === 0) {
      return true;
    }
    await delayFn(100);
  }
  return (await listeningPidsFn(port)).length === 0;
}

export async function terminateManagedEmbeddedRuntimeForPort(port, {
  env = process.env,
  allowedParentPids = [1],
  listeningPidsFn = listeningPidsForPort,
  inspectProcessFn = inspectProcessIdentity,
  killProcess = (pid, signal) => process.kill(pid, signal),
  delayFn = delay,
  waitForPortReleaseFn = waitForPortRelease,
} = {}) {
  const managedPids = await managedEmbeddedRuntimePidsForPort(port, {
    env,
    allowedParentPids,
    listeningPidsFn,
    inspectProcessFn,
  });
  if (managedPids.length === 0) {
    return { matched: false, terminated: false, pids: [] };
  }
  for (const pid of managedPids) {
    try {
      killProcess(pid, "SIGTERM");
    } catch {
      // A verified process may exit between inspection and signaling.
    }
  }
  const termDeadline = Date.now() + MANAGED_PROCESS_TERM_WAIT_MS;
  while (Date.now() < termDeadline) {
    const remaining = await managedEmbeddedRuntimePidsForPort(port, {
      env,
      allowedParentPids: [1, ...managedPids],
      listeningPidsFn,
      inspectProcessFn,
    });
    if (remaining.length === 0) {
      return { matched: true, terminated: true, pids: managedPids };
    }
    await delayFn(50);
  }
  const remaining = await managedEmbeddedRuntimePidsForPort(port, {
    env,
    allowedParentPids: [1, ...managedPids],
    listeningPidsFn,
    inspectProcessFn,
  });
  for (const pid of remaining) {
    try {
      killProcess(pid, "SIGKILL");
    } catch {
      // The final port readback below is authoritative.
    }
  }
  const terminated = await waitForPortReleaseFn(port, { listeningPidsFn, delayFn });
  return { matched: true, terminated, pids: managedPids };
}
