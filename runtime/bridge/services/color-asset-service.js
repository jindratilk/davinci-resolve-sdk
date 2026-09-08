import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import {
  ensurePrivateDirectory,
  writePrivateJsonAtomic,
} from "./private-storage.js";

export const DEFAULT_COLOR_ASSET_CACHE_LIMIT_BYTES = 10 * 1024 * 1024 * 1024;
export const DEFAULT_COLOR_ASSET_AUTO_DOWNLOAD_LIMIT_BYTES = 250 * 1024 * 1024;
export const COLOR_ASSET_DOWNLOAD_MODES = Object.freeze(["automatic", "confirm_large", "confirm_all"]);
const LOCAL_ASSET_EXTENSIONS = new Set([
  ".cube", ".3dl", ".drx", ".dctl", ".setting", ".drfx", ".xml",
  ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".mov", ".mp4", ".mxf",
]);
const LOCAL_ASSET_SCAN_LIMIT = 5_000;

function normalizeString(value) {
  return typeof value === "string" ? value.trim() : "";
}

function positiveInteger(value) {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function safeFileName(value) {
  const normalized = path.basename(normalizeString(value) || "asset.bin")
    .replace(/[\r\n\\/]+/g, "-")
    .replace(/[^\p{L}\p{N}._ -]+/gu, "-")
    .trim()
    .slice(0, 180);
  return normalized || "asset.bin";
}

function readIndex(indexPath) {
  try {
    const parsed = JSON.parse(fs.readFileSync(indexPath, "utf8"));
    return parsed && typeof parsed === "object" && parsed.version === 1 && parsed.objects
      ? parsed
      : { version: 1, objects: {} };
  } catch {
    return { version: 1, objects: {} };
  }
}

async function sha256File(filePath) {
  const hash = createHash("sha256");
  for await (const chunk of fs.createReadStream(filePath)) {
    hash.update(chunk);
  }
  return hash.digest("hex");
}

function downloadMode(settingsService) {
  const configured = settingsService?.getAppSettings?.()?.non_secret_runtime_preferences?.color_asset_download_mode;
  return COLOR_ASSET_DOWNLOAD_MODES.includes(configured) ? configured : "confirm_large";
}

function cacheLimitBytes(settingsService) {
  const configuredGb = Number(
    settingsService?.getAppSettings?.()?.non_secret_runtime_preferences?.color_asset_cache_limit_gb,
  );
  return Number.isFinite(configuredGb) && configuredGb >= 1 && configuredGb <= 500
    ? Math.round(configuredGb * 1024 * 1024 * 1024)
    : DEFAULT_COLOR_ASSET_CACHE_LIMIT_BYTES;
}

function requiresConfirmation({ sizeBytes, mode }) {
  return mode === "confirm_all"
    || (mode === "confirm_large" && sizeBytes > DEFAULT_COLOR_ASSET_AUTO_DOWNLOAD_LIMIT_BYTES);
}

function requireAccessToken(authService) {
  const token = authService?.getAccessToken?.();
  if (!token) throw new Error("Sign in to CutAgent AI before using the color asset library.");
  return token;
}

function localAssetType(filePath) {
  const normalized = filePath.toLowerCase();
  const ext = path.extname(normalized);
  if (ext === ".cube" || ext === ".3dl") {
    return /(technical|transform|conversion|camera|log|rec[._ -]?709|aces|cst)/.test(normalized)
      ? "technical_lut"
      : "creative_lut";
  }
  if (ext === ".drx") return "powergrade";
  if (ext === ".dctl") return "dctl";
  if ([".setting", ".drfx", ".xml"].includes(ext)) return "resolve_preset";
  if ([".mov", ".mp4", ".mxf"].includes(ext)) {
    return /(grain|film.?scan|16mm|8mm|35mm)/.test(normalized) ? "film_grain" : "overlay";
  }
  return /(overlay|light leak|burn|dust|scratch)/.test(normalized) ? "overlay" : "texture";
}

function matchesLocalSearch(asset, input = {}) {
  const types = Array.isArray(input.types) ? input.types.filter(Boolean) : [];
  if (types.length > 0 && !types.includes(asset.type)) return false;
  const terms = [input.query, input.expected_input, ...(Array.isArray(input.tags) ? input.tags : [])]
    .filter((value) => typeof value === "string" && value.trim())
    .flatMap((value) => value.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((term) => term.length > 1));
  if (terms.length === 0) return true;
  const text = `${asset.name} ${asset.collection ?? ""} ${asset.type}`.toLowerCase();
  return terms.some((term) => text.includes(term));
}

export function createColorAssetService({
  storageDir,
  settingsService,
  authService,
  cutagentCloudService,
  fetchImpl = fetch,
}) {
  if (!normalizeString(storageDir)) throw new Error("Color asset cache storageDir is required.");
  const rootDir = path.resolve(storageDir);
  const objectsDir = path.join(rootDir, "objects");
  const partialsDir = path.join(rootDir, "partials");
  const indexPath = path.join(rootDir, "index.json");
  const localIndexPath = path.join(rootDir, "local-index.json");
  ensurePrivateDirectory(rootDir);
  ensurePrivateDirectory(objectsDir);
  ensurePrivateDirectory(partialsDir);

  function loadIndex() {
    const index = readIndex(indexPath);
    let changed = false;
    for (const [hash, entry] of Object.entries(index.objects)) {
      if (!entry || typeof entry.path !== "string" || !fs.existsSync(entry.path)) {
        delete index.objects[hash];
        changed = true;
      }
    }
    if (changed) writePrivateJsonAtomic(indexPath, index);
    return index;
  }

  function cachedEntry(sha256) {
    const hash = normalizeString(sha256).toLowerCase();
    const index = loadIndex();
    const entry = index.objects[hash];
    if (!entry || !fs.existsSync(entry.path)) return null;
    entry.last_accessed_at = new Date().toISOString();
    writePrivateJsonAtomic(indexPath, index);
    return { ...entry };
  }

  function enforceLimit({ preserveHash = null } = {}) {
    const index = loadIndex();
    const entries = Object.entries(index.objects)
      .filter(([, entry]) => entry && fs.existsSync(entry.path));
    let totalBytes = entries.reduce((sum, [, entry]) => sum + (positiveInteger(entry.size_bytes) ?? 0), 0);
    const limitBytes = cacheLimitBytes(settingsService);
    const removed = [];
    for (const [hash, entry] of entries.sort((left, right) => (
      Date.parse(left[1].last_accessed_at ?? 0) - Date.parse(right[1].last_accessed_at ?? 0)
    ))) {
      if (totalBytes <= limitBytes) break;
      if (hash === preserveHash || entry.pinned) continue;
      try {
        fs.rmSync(entry.path, { force: true });
      } catch {
        continue;
      }
      totalBytes -= positiveInteger(entry.size_bytes) ?? 0;
      delete index.objects[hash];
      removed.push(hash);
    }
    writePrivateJsonAtomic(indexPath, index);
    return { totalBytes, limitBytes, removed };
  }

  function localAssetRoot() {
    const configured = settingsService?.getAppSettings?.()?.non_secret_runtime_preferences?.cutagent_folder;
    return normalizeString(configured) ? path.join(path.resolve(configured), "Color Assets") : null;
  }

  async function scanLocalAssets(input = {}, maxResults = 10) {
    const sourceRoot = localAssetRoot();
    if (!sourceRoot || !fs.existsSync(sourceRoot)) return [];
    const previous = (() => {
      try {
        const parsed = JSON.parse(fs.readFileSync(localIndexPath, "utf8"));
        return parsed?.version === 1 && parsed.files ? parsed.files : {};
      } catch {
        return {};
      }
    })();
    const next = {};
    const files = [];
    const stack = [sourceRoot];
    while (stack.length > 0 && files.length < LOCAL_ASSET_SCAN_LIMIT) {
      const directory = stack.pop();
      let entries = [];
      try { entries = fs.readdirSync(directory, { withFileTypes: true }); } catch { continue; }
      for (const entry of entries) {
        if (entry.isSymbolicLink()) continue;
        const absolutePath = path.join(directory, entry.name);
        if (entry.isDirectory()) stack.push(absolutePath);
        else if (entry.isFile() && LOCAL_ASSET_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) files.push(absolutePath);
        if (files.length >= LOCAL_ASSET_SCAN_LIMIT) break;
      }
    }
    const assets = [];
    for (const absolutePath of files.sort()) {
      let stat;
      try { stat = fs.statSync(absolutePath); } catch { continue; }
      const relativePath = path.relative(sourceRoot, absolutePath);
      const cacheKey = `${stat.size}:${stat.mtimeMs}`;
      const cached = previous[relativePath];
      const sha256 = cached?.cache_key === cacheKey && /^[0-9a-f]{64}$/.test(cached.sha256)
        ? cached.sha256
        : await sha256File(absolutePath);
      next[relativePath] = { cache_key: cacheKey, sha256 };
      const id = `local:${sha256}`;
      const asset = {
        id,
        slug: id,
        source: "local_user",
        type: localAssetType(relativePath),
        name: path.basename(relativePath, path.extname(relativePath)).replace(/[_-]+/g, " "),
        description: "Private user-owned local color asset.",
        collection: path.dirname(relativePath) === "." ? null : path.dirname(relativePath),
        author: null,
        tags: ["local", "user-owned"],
        useFor: [],
        avoidWhen: [],
        look: {},
        technical: { source: "local_user" },
        applicationMethod: null,
        previews: [],
        files: [{
          id,
          variantName: "main",
          fileName: path.basename(relativePath),
          fileFormat: path.extname(relativePath).slice(1).toLowerCase(),
          mediaType: "application/octet-stream",
          sha256,
          sizeBytes: stat.size,
          width: null,
          height: null,
          fps: null,
          platform: process.platform,
          localPath: absolutePath,
        }],
        publishedAt: null,
      };
      if (matchesLocalSearch(asset, input)) assets.push(asset);
    }
    writePrivateJsonAtomic(localIndexPath, { version: 1, files: next });
    const requestedLimit = Number.isInteger(Number(input.limit)) ? Number(input.limit) : maxResults;
    return assets.slice(0, Math.max(1, Math.min(maxResults, requestedLimit)));
  }

  async function getLocalAsset(assetId) {
    const normalized = normalizeString(assetId);
    if (!normalized.startsWith("local:")) return null;
    return (await scanLocalAssets({}, LOCAL_ASSET_SCAN_LIMIT)).find((asset) => asset.id === normalized) ?? null;
  }

  async function downloadIntent(intent, { confirmed = false, pin = false } = {}) {
    const sha256 = normalizeString(intent?.sha256).toLowerCase();
    const sizeBytes = positiveInteger(intent?.sizeBytes ?? intent?.size_bytes);
    const downloadUrl = normalizeString(intent?.downloadUrl ?? intent?.download_url);
    const fileName = safeFileName(intent?.fileName ?? intent?.file_name);
    if (!/^[0-9a-f]{64}$/.test(sha256) || !sizeBytes || !downloadUrl) {
      throw new Error("CutAgent cloud returned an invalid color asset download intent.");
    }
    const existing = cachedEntry(sha256);
    if (existing) return { status: "cached", ...existing };
    const mode = downloadMode(settingsService);
    if (!confirmed && requiresConfirmation({ sizeBytes, mode })) {
      return {
        status: "confirmation_required",
        sha256,
        file_name: fileName,
        size_bytes: sizeBytes,
        threshold_bytes: DEFAULT_COLOR_ASSET_AUTO_DOWNLOAD_LIMIT_BYTES,
        download_mode: mode,
      };
    }

    const objectDir = path.join(objectsDir, sha256.slice(0, 2), sha256);
    ensurePrivateDirectory(objectDir);
    const finalPath = path.join(objectDir, fileName);
    const partialPath = path.join(partialsDir, `${sha256}.partial`);
    let partialSize = 0;
    try {
      partialSize = fs.statSync(partialPath).size;
      if (partialSize >= sizeBytes) {
        fs.rmSync(partialPath, { force: true });
        partialSize = 0;
      }
    } catch {
      partialSize = 0;
    }
    const headers = partialSize > 0 ? { Range: `bytes=${partialSize}-` } : {};
    let response = await fetchImpl(downloadUrl, { method: "GET", headers });
    if (partialSize > 0 && response.status !== 206) {
      fs.rmSync(partialPath, { force: true });
      partialSize = 0;
      response = await fetchImpl(downloadUrl, { method: "GET" });
    }
    if (!response.ok || !response.body) {
      throw new Error(`Color asset download failed (${response.status}).`);
    }
    await pipeline(
      Readable.fromWeb(response.body),
      fs.createWriteStream(partialPath, { flags: partialSize > 0 ? "a" : "w", mode: 0o600 }),
    );
    const downloadedSize = fs.statSync(partialPath).size;
    if (downloadedSize !== sizeBytes) {
      throw new Error(`Color asset download size mismatch: expected ${sizeBytes}, received ${downloadedSize}.`);
    }
    const downloadedHash = await sha256File(partialPath);
    if (downloadedHash !== sha256) {
      fs.rmSync(partialPath, { force: true });
      throw new Error("Color asset download failed SHA-256 verification.");
    }
    fs.renameSync(partialPath, finalPath);
    try { fs.chmodSync(finalPath, 0o600); } catch {}
    const index = loadIndex();
    index.objects[sha256] = {
      path: finalPath,
      file_name: fileName,
      size_bytes: sizeBytes,
      media_type: normalizeString(intent?.mediaType ?? intent?.media_type) || "application/octet-stream",
      pinned: Boolean(pin),
      last_accessed_at: new Date().toISOString(),
    };
    writePrivateJsonAtomic(indexPath, index);
    enforceLimit({ preserveHash: sha256 });
    return { status: "downloaded", sha256, ...index.objects[sha256] };
  }

  return {
    async search(input = {}) {
      const [cloud, local] = await Promise.all([
        cutagentCloudService.searchColorAssets(requireAccessToken(authService), input),
        scanLocalAssets(input),
      ]);
      const cloudResults = Array.isArray(cloud?.results) ? cloud.results : [];
      return { ...cloud, results: [...local, ...cloudResults].slice(0, 10) };
    },
    async get(assetId) {
      const local = await getLocalAsset(assetId);
      if (local) return { ok: true, asset: local };
      return cutagentCloudService.getColorAsset(requireAccessToken(authService), assetId);
    },
    async ensure({ assetId, fileId, purpose = "download", confirmed = false, pin = false }) {
      const local = await getLocalAsset(assetId);
      if (local) {
        const file = local.files.find((candidate) => candidate.id === fileId);
        if (!file) throw new Error("Private local color asset file was not found.");
        const currentHash = await sha256File(file.localPath);
        if (currentHash !== file.sha256) throw new Error("Private local color asset changed during validation; search again before applying it.");
        return {
          status: "local_user",
          path: file.localPath,
          sha256: file.sha256,
          file_name: file.fileName,
          size_bytes: file.sizeBytes,
          user_owned: true,
        };
      }
      const intent = await cutagentCloudService.createColorAssetDownloadIntent(
        requireAccessToken(authService),
        assetId,
        { file_id: fileId, purpose },
      );
      return downloadIntent(intent, { confirmed, pin });
    },
    async ensurePreview({ assetId, previewId, confirmed = false }) {
      const intent = await cutagentCloudService.createColorAssetPreviewIntent(
        requireAccessToken(authService),
        assetId,
        { preview_id: previewId },
      );
      return downloadIntent(intent, { confirmed, pin: false });
    },
    getCached(sha256) {
      return cachedEntry(sha256);
    },
    scanLocalAssets,
    getStatus() {
      const index = loadIndex();
      const objects = Object.entries(index.objects);
      return {
        object_count: objects.length,
        size_bytes: objects.reduce((sum, [, entry]) => sum + (positiveInteger(entry.size_bytes) ?? 0), 0),
        limit_bytes: cacheLimitBytes(settingsService),
        download_mode: downloadMode(settingsService),
        automatic_limit_bytes: DEFAULT_COLOR_ASSET_AUTO_DOWNLOAD_LIMIT_BYTES,
      };
    },
    enforceLimit,
  };
}
