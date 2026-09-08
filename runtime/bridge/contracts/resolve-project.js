function normalizeString(value) {
  return typeof value === "string" ? value.trim() : "";
}

export function normalizeDatabaseDetails(raw) {
  if (!raw || typeof raw !== "object") {
    return {
      database_type: null,
      database_name: null,
    };
  }

  const databaseType = normalizeString(raw.database_type ?? raw.DbType);
  const databaseName = normalizeString(raw.database_name ?? raw.DbName);

  return {
    database_type: databaseType || null,
    database_name: databaseName || null,
  };
}

export function buildResolveProjectKey(project) {
  const name = normalizeString(project?.name);
  const { database_type, database_name } = normalizeDatabaseDetails(project);
  if (!name) {
    return null;
  }
  return [
    database_type || "unknown-db-type",
    database_name || "unknown-db-name",
    name,
  ].join("::");
}

export function normalizeResolveProject(project, fallbackStatus = "inactive") {
  if (!project || typeof project !== "object") {
    return null;
  }

  const name = normalizeString(project.name ?? project.project_name ?? project.resolve_project_name);
  if (!name) {
    return null;
  }

  const { database_type, database_name } = normalizeDatabaseDetails(project);
  const status = normalizeString(project.status) || fallbackStatus;
  const key = normalizeString(project.key) || buildResolveProjectKey({
    name,
    database_type,
    database_name,
  });

  return {
    key,
    name,
    database_type,
    database_name,
    status: status || fallbackStatus,
  };
}

export function legacyResolveProjectFromName(name) {
  const normalizedName = normalizeString(name);
  if (!normalizedName) {
    return null;
  }

  return {
    key: buildResolveProjectKey({
      name: normalizedName,
      database_type: null,
      database_name: null,
    }),
    name: normalizedName,
    database_type: null,
    database_name: null,
    status: "inactive",
  };
}

export function setResolveProjectStatus(project, status) {
  const normalized = normalizeResolveProject(project);
  if (!normalized) {
    return null;
  }
  return {
    ...normalized,
    status,
  };
}

export function areResolveProjectsEqual(left, right) {
  const normalizedLeft = normalizeResolveProject(left);
  const normalizedRight = normalizeResolveProject(right);
  if (!normalizedLeft || !normalizedRight) {
    return false;
  }

  if (normalizedLeft.key && normalizedRight.key) {
    return normalizedLeft.key === normalizedRight.key;
  }

  return normalizedLeft.name === normalizedRight.name
    && normalizedLeft.database_type === normalizedRight.database_type
    && normalizedLeft.database_name === normalizedRight.database_name;
}
