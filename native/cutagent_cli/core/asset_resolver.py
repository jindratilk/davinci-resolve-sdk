"""Read-only fallback asset resolution across files, Fusion templates, and Media Pool."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from ..errors import ValidationError

SUPPORTED_TYPES = {"template", "media", "file", "custom-media"}
SUPPORTED_KINDS = {"fusion-template", "title", "image", "video", "audio", "any"}

IMAGE_EXTENSIONS = {".bmp", ".cin", ".dng", ".gif", ".heic", ".jpeg", ".jpg", ".png", ".psd", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".avi", ".braw", ".m4v", ".mkv", ".mov", ".mp4", ".mxf", ".r3d", ".webm"}
AUDIO_EXTENSIONS = {".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}


def default_template_directories() -> list[str]:
    """Return the user and bundled Fusion template directories used by CLI lookup."""
    user_dir = os.environ.get("RESOLVE_TEMPLATE_DIR", os.path.expanduser("~/resolve-templates"))
    bundled_dir = Path(__file__).resolve().parents[1] / "assets" / "fusion-templates"
    directories = [user_dir, str(bundled_dir)]
    seen: set[str] = set()
    normalized: list[str] = []
    for directory in directories:
        resolved = os.path.abspath(os.path.expanduser(str(directory)))
        if resolved in seen:
            continue
        seen.add(resolved)
        normalized.append(resolved)
    return normalized


def resolve_asset_candidates(
    conn,
    candidates,
    require: bool = False,
    *,
    mode: str = "first",
    template_directories: Iterable[str] | None = None,
) -> dict[str, Any]:
    """DaVinci Resolve candidate assets in order without mutating DaVinci Resolve."""
    if mode not in {"first", "all"}:
        raise ValidationError("Unsupported asset resolve mode.", details={"mode": mode, "allowed": ["first", "all"]})
    if not isinstance(candidates, list):
        raise ValidationError("Asset candidates must be a JSON array.", details={"type": type(candidates).__name__})

    attempts: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    resolved_assets: list[dict[str, Any]] = []
    template_dirs = list(template_directories) if template_directories is not None else default_template_directories()

    for index, raw_candidate in enumerate(candidates):
        attempt = _resolve_one_candidate(conn, raw_candidate, index=index, template_directories=template_dirs)
        attempts.append(attempt)
        if attempt.get("found") and not attempt.get("ambiguous"):
            asset = _selected_from_attempt(attempt)
            resolved_assets.append(asset)
            if selected is None:
                selected = asset
            if mode == "first":
                break

    payload: dict[str, Any] = {
        "selected": selected,
        "attempts": attempts,
        "required": bool(require),
        "mode": mode,
    }
    if mode == "all":
        payload["resolved"] = resolved_assets
    return payload


def _resolve_one_candidate(conn, candidate: Any, *, index: int, template_directories: list[str]) -> dict[str, Any]:
    base: dict[str, Any] = {"index": index, "found": False}
    if not isinstance(candidate, dict):
        return {**base, "reason": "invalid_candidate", "details": {"candidate_type": type(candidate).__name__}}

    candidate_type = _optional_text(candidate.get("type"))
    if not candidate_type:
        return {**base, "reason": "invalid_candidate", "details": {"missing": "type"}}
    if candidate_type not in SUPPORTED_TYPES:
        return {**base, "type": candidate_type, "reason": "unsupported_type"}

    kind = _normalize_kind(candidate.get("kind"))
    if kind == "__invalid__":
        return {**base, "type": candidate_type, "reason": "invalid_candidate", "details": {"kind": candidate.get("kind"), "allowed": sorted(SUPPORTED_KINDS)}}

    if candidate_type == "file":
        return _resolve_file_candidate(candidate, index=index, kind=kind)
    if candidate_type == "template":
        return _resolve_template_candidate(candidate, index=index, template_directories=template_directories)
    if candidate_type == "media":
        return _resolve_media_candidate(conn, candidate, index=index, kind=kind)
    return _resolve_custom_media_candidate(conn, candidate, index=index, kind=kind)


def _selected_from_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    selected = {
        "type": attempt.get("type"),
        "name": attempt.get("name"),
        "candidate_index": attempt.get("index"),
    }
    for key in ("path", "folder", "kind", "source_path", "custom"):
        if attempt.get(key) is not None:
            selected[key] = attempt.get(key)
    return selected


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_kind(value: Any) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    normalized = text.lower().replace("_", "-")
    return normalized if normalized in SUPPORTED_KINDS else "__invalid__"


def _name_variants(name: str) -> list[str]:
    variants = [name]
    if not name.lower().endswith(".setting"):
        variants.append(f"{name}.setting")
    return variants


def _looks_like_path(value: str) -> bool:
    return os.path.isabs(value) or os.sep in value or (os.altsep is not None and os.altsep in value) or value.startswith("~")


def _canonical_file_path(path: str) -> str | None:
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        return None
    return str(candidate.resolve())


def _resolve_file_candidate(candidate: dict[str, Any], *, index: int, kind: str | None) -> dict[str, Any]:
    requested = _optional_text(candidate.get("path")) or _optional_text(candidate.get("name"))
    if not requested:
        return {"index": index, "type": "file", "found": False, "reason": "invalid_candidate", "details": {"missing": "path"}}
    path = _canonical_file_path(requested)
    if path is None:
        return {"index": index, "type": "file", "name": candidate.get("name"), "path": requested, "found": False, "reason": "file_not_found"}
    return {"index": index, "type": "file", "name": _optional_text(candidate.get("name")) or Path(path).name, "path": path, "kind": kind, "found": True}


def _resolve_template_candidate(candidate: dict[str, Any], *, index: int, template_directories: list[str]) -> dict[str, Any]:
    requested = _optional_text(candidate.get("path")) or _optional_text(candidate.get("name"))
    if not requested:
        return {"index": index, "type": "template", "found": False, "reason": "invalid_candidate", "details": {"missing": "name"}}

    path_candidates: list[str] = []
    if _looks_like_path(requested):
        path_candidates.extend(os.path.abspath(os.path.expanduser(path)) for path in _name_variants(requested))
    name = _optional_text(candidate.get("name")) or Path(requested).name
    if name:
        for directory in template_directories:
            for variant in _name_variants(name):
                path_candidates.append(os.path.join(directory, variant))

    for path in path_candidates:
        resolved = _canonical_file_path(path)
        if resolved is not None:
            return {"index": index, "type": "template", "name": Path(resolved).name, "path": resolved, "kind": "fusion-template", "found": True}

    matches: list[str] = []
    if name:
        requested_names = {variant.lower() for variant in _name_variants(name)}
        for directory in template_directories:
            if not os.path.isdir(directory):
                continue
            for root, _dirs, files in os.walk(directory):
                for file_name in files:
                    if file_name.lower() in requested_names:
                        matches.append(os.path.abspath(os.path.join(root, file_name)))
    unique_matches = sorted(dict.fromkeys(matches))
    if len(unique_matches) == 1:
        path = str(Path(unique_matches[0]).resolve())
        return {"index": index, "type": "template", "name": Path(path).name, "path": path, "kind": "fusion-template", "found": True}
    if len(unique_matches) > 1:
        return {"index": index, "type": "template", "name": name, "found": False, "reason": "invalid_candidate", "details": {"matches": unique_matches}}

    return {
        "index": index,
        "type": "template",
        "name": name,
        "found": False,
        "reason": "template_not_found",
        "details": {"searched_directories": template_directories, "candidates": path_candidates},
    }


def _resolve_media_candidate(conn, candidate: dict[str, Any], *, index: int, kind: str | None) -> dict[str, Any]:
    if conn is None:
        return {"index": index, "type": "media", "name": candidate.get("name"), "found": False, "reason": "media_not_found", "details": {"requires_project_connection": True}}

    name = _optional_text(candidate.get("name"))
    path = _optional_text(candidate.get("path"))
    if not name and not path:
        return {"index": index, "type": "media", "found": False, "reason": "invalid_candidate", "details": {"required_one_of": ["name", "path"]}}

    try:
        rows = _media_rows(conn, folder=_optional_text(candidate.get("folder")))
    except _FolderMissing as exc:
        return {"index": index, "type": "media", "name": name, "folder": exc.folder, "found": False, "reason": "folder_not_found"}

    exact = bool(candidate.get("exact", False))
    include_generated = not bool(candidate.get("exclude_generated", False))
    candidates = rows
    if not include_generated:
        candidates = [row for row in candidates if not row.get("is_generated")]
    if name:
        candidates = [row for row in candidates if _media_name_matches(str(row.get("name") or ""), name, exact=exact)]
    if path:
        candidates = [row for row in candidates if _paths_match(row.get("source_path"), path)]

    pre_kind_count = len(candidates)
    if kind and kind != "any":
        candidates = [row for row in candidates if _media_kind_matches(row, kind)]
    if pre_kind_count and not candidates:
        return {"index": index, "type": "media", "name": name, "path": path, "found": False, "reason": "kind_mismatch", "kind": kind}
    if not candidates:
        return {"index": index, "type": "media", "name": name, "path": path, "found": False, "reason": "media_not_found", "kind": kind}
    if len(candidates) != 1:
        return {
            "index": index,
            "type": "media",
            "name": name,
            "path": path,
            "found": False,
            "reason": "ambiguous_media",
            "ambiguous": True,
            "matches": [_public_media_row(row) for row in candidates],
        }

    row = candidates[0]
    return {"index": index, "type": "media", "found": True, **_public_media_row(row)}


def _resolve_custom_media_candidate(conn, candidate: dict[str, Any], *, index: int, kind: str | None) -> dict[str, Any]:
    entry_slug_candidates = _custom_entry_slug_candidates(candidate.get("entry_identifier"), candidate.get("header"))
    suffix_candidates = _custom_suffix_candidates(candidate.get("suffix"))
    custom = {
        "entry_slug_candidates": entry_slug_candidates,
        "suffix_candidates": suffix_candidates,
    }

    base_attempt = {
        "index": index,
        "type": "custom-media",
        "found": False,
        "folder": _optional_text(candidate.get("folder")),
        "kind": kind,
        "custom": custom,
    }
    if not entry_slug_candidates:
        return {**base_attempt, "reason": "missing_custom_entry"}
    if not suffix_candidates:
        return {**base_attempt, "reason": "invalid_custom_suffix"}
    if conn is None:
        return {**base_attempt, "reason": "custom_media_not_found", "details": {"requires_project_connection": True}}

    try:
        rows = _media_rows(conn, folder=_optional_text(candidate.get("folder")))
    except _FolderMissing as exc:
        return {**base_attempt, "folder": exc.folder, "reason": "folder_not_found"}

    include_generated = not bool(candidate.get("exclude_generated", False))
    candidates = rows if include_generated else [row for row in rows if not row.get("is_generated")]
    pre_kind_count = len(candidates)
    if kind and kind != "any":
        candidates = [row for row in candidates if _media_kind_matches(row, kind)]
    if pre_kind_count and not candidates:
        return {**base_attempt, "reason": "kind_mismatch"}

    allow_prefix_match = bool(candidate.get("allow_prefix_match", True))
    exact_matches: list[dict[str, Any]] = []
    prefix_matches: list[dict[str, Any]] = []

    for row in candidates:
        clip_slug = _slugify_custom_name(str(row.get("name") or ""))
        if not clip_slug:
            continue
        for base_slug in entry_slug_candidates:
            for suffix_slug in suffix_candidates:
                target_slug = f"{base_slug}-{suffix_slug}"
                if clip_slug == target_slug:
                    exact_matches.append({"row": row, "matched_suffix": suffix_slug, "extra_len": 0})
                    continue
                if allow_prefix_match and clip_slug.startswith(f"{target_slug}-"):
                    prefix_matches.append(
                        {
                            "row": row,
                            "matched_suffix": suffix_slug,
                            "extra_len": len(clip_slug) - len(target_slug),
                        }
                    )

    if exact_matches:
        deduped = _dedupe_custom_matches(exact_matches)
        if len(deduped) == 1:
            return _custom_media_success(index, deduped[0], custom=custom, kind=kind, match_mode="exact")
        return _custom_media_ambiguous(index, deduped, custom=custom, kind=kind, folder=_optional_text(candidate.get("folder")))

    if prefix_matches:
        deduped = _dedupe_custom_matches(prefix_matches)
        deduped.sort(key=lambda match: match["extra_len"])
        best_len = deduped[0]["extra_len"]
        best = [match for match in deduped if match["extra_len"] == best_len]
        if len(best) == 1:
            return _custom_media_success(index, best[0], custom=custom, kind=kind, match_mode="prefix")
        return _custom_media_ambiguous(index, best, custom=custom, kind=kind, folder=_optional_text(candidate.get("folder")))

    return {**base_attempt, "reason": "custom_media_not_found"}


def _custom_media_success(index: int, match: dict[str, Any], *, custom: dict[str, Any], kind: str | None, match_mode: str) -> dict[str, Any]:
    row = match["row"]
    media_row = _public_media_row(row)
    custom_payload = {
        **custom,
        "match_mode": match_mode,
        "matched_suffix": match["matched_suffix"],
    }
    media_row["type"] = "custom-media"
    return {
        "index": index,
        "type": "custom-media",
        "found": True,
        **media_row,
        "kind": kind,
        "candidate_index": index,
        "custom": custom_payload,
    }


def _custom_media_ambiguous(
    index: int,
    matches: list[dict[str, Any]],
    *,
    custom: dict[str, Any],
    kind: str | None,
    folder: str | None,
) -> dict[str, Any]:
    return {
        "index": index,
        "type": "custom-media",
        "found": False,
        "reason": "ambiguous_custom_media",
        "ambiguous": True,
        "folder": folder,
        "kind": kind,
        "custom": custom,
        "matches": [_public_media_row(match["row"]) | {"matched_suffix": match["matched_suffix"]} for match in matches],
    }


def _dedupe_custom_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for match in matches:
        row = match["row"]
        key = (row.get("folder"), row.get("name"), row.get("source_path"), match.get("matched_suffix"), match.get("extra_len"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(match)
    return deduped


def _slugify_custom_name(value: str) -> str:
    if not value or not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFD", value)
    ascii_value = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    ascii_value = ascii_value.lower()
    ascii_value = re.sub(r"[^a-z0-9]+", "-", ascii_value)
    ascii_value = re.sub(r"-+", "-", ascii_value).strip("-")
    return ascii_value


def _custom_entry_slug_candidates(entry_identifier, header) -> list[str]:
    raw_candidates: list[str] = []

    def add_raw(value: Any) -> None:
        text = _optional_text(value)
        if not text:
            return
        raw_candidates.extend(
            [
                text,
                text.lower(),
                re.sub(r"\s+", " ", text),
                text.replace("_", " "),
                text.replace("-", " "),
            ]
        )

    add_raw(entry_identifier)
    add_raw(header)

    slug_candidates: list[str] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        slug = _slugify_custom_name(raw)
        if slug and slug not in seen:
            slug_candidates.append(slug)
            seen.add(slug)
    return slug_candidates


def _custom_suffix_candidates(suffix) -> list[str]:
    normalized = _optional_text(suffix)
    if not normalized:
        return []
    normalized = normalized.lower().replace("_", "-")
    if normalized in {"text", "t", "t-databaze"}:
        return ["text", "t", "t-databaze"]
    if normalized in {"header", "h", "h-databaze"}:
        return ["header", "h", "h-databaze"]
    if normalized in {"image", "i", "i-databaze"}:
        return ["image", "i", "i-databaze"]
    return []


class _FolderMissing(Exception):
    def __init__(self, folder: str):
        super().__init__(folder)
        self.folder = folder


def _media_rows(conn, *, folder: str | None) -> list[dict[str, Any]]:
    media_pool = getattr(conn, "media_pool", None)
    root = media_pool.GetRootFolder() if media_pool is not None and hasattr(media_pool, "GetRootFolder") else None
    if root is None:
        return []
    start_folder = _find_folder(root, folder) if folder else root
    if start_folder is None:
        raise _FolderMissing(folder or "")
    rows: list[dict[str, Any]] = []
    _collect_media_rows(start_folder, "", rows)
    return rows


def _find_folder(root, folder: str | None):
    if not folder:
        return root
    target = str(folder).strip().strip("/")
    if not target:
        return root
    segments = [segment for segment in target.split("/") if segment]
    if hasattr(root, "GetName") and segments and root.GetName() == segments[0]:
        segments = segments[1:]
    current = root
    for segment in segments:
        found = None
        for subfolder in current.GetSubFolderList() or []:
            if hasattr(subfolder, "GetName") and subfolder.GetName() == segment:
                found = subfolder
                break
        if found is None:
            return None
        current = found
    return current


def _collect_media_rows(folder, parent_path: str, rows: list[dict[str, Any]]) -> None:
    folder_name = folder.GetName() if hasattr(folder, "GetName") else ""
    current_path = f"{parent_path}/{folder_name}" if parent_path else str(folder_name)
    for clip in folder.GetClipList() or []:
        props = _clip_properties(clip)
        name = clip.GetName() if hasattr(clip, "GetName") else ""
        clip_type = str(props.get("Type") or "")
        rows.append(
            {
                "name": name,
                "folder": current_path,
                "type_label": clip_type,
                "source_path": _source_path(props, clip),
                "is_generated": _is_generated(name, clip_type),
            }
        )
    for subfolder in folder.GetSubFolderList() or []:
        _collect_media_rows(subfolder, current_path, rows)


def _clip_properties(clip) -> dict[str, Any]:
    try:
        props = clip.GetClipProperty()
    except Exception:
        props = None
    return props if isinstance(props, dict) else {}


def _source_path(props: dict[str, Any], clip) -> str | None:
    for key in ("File Path", "Source File", "SourcePath"):
        value = props.get(key)
        if not value and hasattr(clip, "GetClipProperty"):
            try:
                value = clip.GetClipProperty(key)
            except Exception:
                value = None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_generated(name: str, clip_type: str) -> bool:
    lowered_name = str(name or "").lower()
    lowered_type = str(clip_type or "").lower()
    return lowered_name.startswith("resolve_") or "generated" in lowered_type


def _media_name_matches(actual: str, requested: str, *, exact: bool) -> bool:
    if exact:
        return actual == requested
    return requested.casefold() in actual.casefold()


def _paths_match(actual: Any, requested: str) -> bool:
    if not actual:
        return False
    actual_text = str(actual)
    requested_text = str(requested)
    try:
        return Path(actual_text).expanduser().resolve() == Path(requested_text).expanduser().resolve()
    except Exception:
        return actual_text == requested_text


def _media_kind_matches(row: dict[str, Any], kind: str) -> bool:
    if kind == "fusion-template":
        return False
    name = str(row.get("name") or "")
    type_label = str(row.get("type_label") or "")
    source_path = str(row.get("source_path") or "")
    lowered = f"{name} {type_label}".casefold()
    suffix = Path(source_path).suffix.casefold()
    if kind == "title":
        return "title" in lowered or "text+" in lowered or "text plus" in lowered or "fusion composition" in lowered
    if kind == "image":
        return suffix in IMAGE_EXTENSIONS or "still" in lowered or "image" in lowered
    if kind == "video":
        return suffix in VIDEO_EXTENSIONS or "video" in lowered or "movie" in lowered
    if kind == "audio":
        return suffix in AUDIO_EXTENSIONS or "audio" in lowered or "sound" in lowered
    return True


def _public_media_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "type": "media",
        "name": row.get("name"),
        "folder": row.get("folder"),
        "source_path": row.get("source_path"),
    }
    if row.get("type_label"):
        payload["media_type"] = row.get("type_label")
    return payload
