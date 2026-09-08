import path from "node:path";

function normalizeString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

export function getSessionUserStoragePaths(session = null) {
  const userSessionDir = normalizeString(session?.user_session_path);
  if (!userSessionDir) {
    return null;
  }
  return {
    sessionDir: userSessionDir,
    uploadsDir: path.join(userSessionDir, "uploads"),
    exportsDir: path.join(userSessionDir, "exports"),
  };
}

export function getSessionRuntimeEnv(session = null) {
  const paths = getSessionUserStoragePaths(session);
  const instance = session?.resolve_runtime?.mode === "parallel_gui_beta" ? session.resolve_runtime : null;
  return {
    ...(paths ? {
        CUTAGENT_USER_SESSION_DIR: paths.sessionDir,
        CUTAGENT_USER_UPLOADS_DIR: paths.uploadsDir,
        CUTAGENT_USER_EXPORTS_DIR: paths.exportsDir,
      } : {}),
    ...(instance ? {
      HOME: instance.home,
      CFFIXED_USER_HOME: instance.home,
      TMPDIR: `${instance.tmp}${path.sep}`,
      CUTAGENT_RESOLVE_UUID: instance.uuid,
      CUTAGENT_RESOLVE_PID: String(instance.pid),
      ...(instance.host ? { CUTAGENT_RESOLVE_HOST: instance.host } : {}),
    } : {}),
  };
}

function hasOption(args, names) {
  return args.some((arg) => names.some((name) => arg === name || arg.startsWith(`${name}=`)));
}

function commandTokens(args) {
  return args.filter((arg) => typeof arg === "string" && arg.trim() && !arg.trim().startsWith("-"));
}

export function applySessionExportDefaults(args, session = null) {
  if (!Array.isArray(args) || args.length === 0) {
    return args;
  }
  const paths = getSessionUserStoragePaths(session);
  if (!paths) {
    return args;
  }
  const [group, action] = commandTokens(args);
  if (group === "render" && action === "quick-export" && !hasOption(args, ["--output", "-o"])) {
    return [...args, "--output", paths.exportsDir];
  }
  return args;
}

export function getSessionCommandCwd(settingsService, session = null) {
  const workspacePath = normalizeString(session?.agent_workspace_path);
  if (workspacePath) {
    return workspacePath;
  }
  return settingsService?.getAppSettings?.()?.non_secret_runtime_preferences?.managed_workspace_root || process.cwd();
}
