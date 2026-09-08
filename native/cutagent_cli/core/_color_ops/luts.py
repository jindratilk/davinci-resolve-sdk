from __future__ import annotations

import hashlib
import os
import shutil
from typing import Any, Dict, Optional, Tuple

from ...errors import APICallFailed, ClipNotFound, ValidationError
from ...policy import require_api_method


def _normalize_lut_key(value: str) -> str:
    return str(value).strip().replace("\\", "/")


def _dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _resolve_lut_root_entries(*, ops_module) -> list[Dict[str, str]]:
    raw_roots = [
        ("system", getattr(ops_module, "_SYSTEM_RESOLVE_LUT_ROOT", None)),
        ("user", getattr(ops_module, "_USER_RESOLVE_LUT_ROOT", None)),
    ]
    entries: list[Dict[str, str]] = []
    seen = set()
    for kind, root in raw_roots:
        if not root:
            continue
        abs_root = os.path.abspath(os.path.expanduser(str(root)))
        if abs_root in seen:
            continue
        seen.add(abs_root)
        entries.append({"kind": kind, "root": abs_root})
    return entries


def _resolve_lut_roots(*, ops_module) -> list[str]:
    return [entry["root"] for entry in _resolve_lut_root_entries(ops_module=ops_module)]


def _relative_lut_entry_for_known_root(path: str, *, ops_module) -> Optional[Dict[str, str]]:
    abs_path = os.path.abspath(os.path.expanduser(path))
    for entry in _resolve_lut_root_entries(ops_module=ops_module):
        root = entry["root"]
        try:
            common = os.path.commonpath([abs_path, root])
        except ValueError:
            continue
        if common == root:
            return {
                "lut_path": _normalize_lut_key(os.path.relpath(abs_path, root)),
                "root_kind": entry["kind"],
                "root_path": root,
                "source": "known_root",
            }
    return None


def _relative_lut_key_for_known_root(path: str, *, ops_module) -> Optional[str]:
    entry = _relative_lut_entry_for_known_root(path, ops_module=ops_module)
    return entry["lut_path"] if entry else None


def _nearest_existing_parent(path: str) -> str:
    current = os.path.abspath(os.path.expanduser(path))
    while not os.path.exists(current):
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return current


def _lut_root_is_writable(root: str) -> bool:
    abs_root = os.path.abspath(os.path.expanduser(root))
    if os.path.isdir(abs_root):
        return os.access(abs_root, os.W_OK | os.X_OK)
    parent = _nearest_existing_parent(abs_root)
    return os.path.isdir(parent) and os.access(parent, os.W_OK | os.X_OK)


def _install_lut_root_candidates(*, ops_module, exclude_roots: Optional[set[str]] = None) -> list[Dict[str, Any]]:
    exclude = exclude_roots or set()
    entries = [
        {**entry, "writable": _lut_root_is_writable(entry["root"])}
        for entry in _resolve_lut_root_entries(ops_module=ops_module)
        if entry["root"] not in exclude
    ]
    writable_entries = [entry for entry in entries if entry["writable"]]
    if writable_entries:
        return writable_entries

    # Preserve the old user-root fallback when writability probing is inconclusive.
    user_entries = [entry for entry in entries if entry["kind"] == "user"]
    return user_entries or entries


def _refresh_lut_list_best_effort(conn, *, ops_module) -> Optional[str]:
    project = getattr(conn, "project", None)
    refresher = getattr(project, "RefreshLUTList", None)
    if not callable(refresher):
        return "RefreshLUTList is not available."
    try:
        result = refresher()
        if result is False:
            return "RefreshLUTList returned False."
    except Exception as exc:
        return str(exc)
    return None


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_lut_library_folder(folder: str) -> str:
    raw = str(folder or "").strip().replace("\\", "/")
    if not raw:
        raw = "CutAgent/Imported"
    raw = raw.strip("/")
    parts = [part for part in raw.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValidationError(
            "LUT library folder must be a relative DaVinci Resolve LUT folder.",
            details={"folder": folder},
        )
    return "/".join(parts)


def _lut_library_source_files(source_path: str) -> tuple[str, list[tuple[str, str]]]:
    root = os.path.abspath(os.path.expanduser(str(source_path).strip()))
    if not root:
        raise ValidationError("LUT library source path must not be empty.", details={"source": source_path})
    if os.path.isfile(root):
        if not root.lower().endswith(".cube"):
            raise ValidationError(
                "LUT library import currently supports .cube files.",
                details={"source": source_path, "resolved_path": root},
            )
        return root, [(root, os.path.basename(root))]
    if not os.path.isdir(root):
        raise ValidationError(
            "LUT library source path was not found.",
            details={"source": source_path, "resolved_path": root},
        )

    files: list[tuple[str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in sorted(filenames):
            if not filename.lower().endswith(".cube"):
                continue
            abs_file = os.path.join(dirpath, filename)
            rel_file = os.path.relpath(abs_file, root).replace("\\", "/")
            files.append((abs_file, rel_file))
    files.sort(key=lambda item: item[1])
    if not files:
        raise ValidationError(
            "LUT library source did not contain any .cube files.",
            details={"source": source_path, "resolved_path": root},
        )
    return root, files


def _copy_lut_library_files(
    source_path: str,
    *,
    folder: str,
    overwrite: bool,
    ops_module,
) -> Dict[str, Any]:
    source_root, source_files = _lut_library_source_files(source_path)
    root_candidates = _install_lut_root_candidates(ops_module=ops_module)
    if not root_candidates:
        raise APICallFailed(
            "No DaVinci Resolve LUT install root is available.",
            details={"source": source_path, "resolve_lut_roots": _resolve_lut_roots(ops_module=ops_module)},
        )
    root_entry = root_candidates[0]
    install_root = os.path.abspath(os.path.expanduser(str(root_entry["root"])))
    library_folder = _validate_lut_library_folder(folder)
    target_root = os.path.join(install_root, *library_folder.split("/"))

    planned: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for abs_source, rel_source in source_files:
        rel_parts = [part for part in rel_source.replace("\\", "/").split("/") if part]
        if any(part in {".", ".."} for part in rel_parts):
            raise ValidationError(
                "LUT library source contains an unsafe relative path.",
                details={"relative_path": rel_source},
            )
        target_path = os.path.join(target_root, *rel_parts)
        source_sha = _file_sha256(abs_source)
        status = "copied"
        existing_sha = None
        if os.path.exists(target_path):
            existing_sha = _file_sha256(target_path)
            if existing_sha == source_sha:
                status = "unchanged"
            elif not overwrite:
                conflicts.append(
                    {
                        "source_path": abs_source,
                        "target_path": target_path,
                        "source_sha256": source_sha,
                        "target_sha256": existing_sha,
                    }
                )
        planned.append(
            {
                "source_path": abs_source,
                "relative_source_path": rel_source,
                "target_path": target_path,
                "lut_key": _normalize_lut_key(os.path.join(library_folder, *rel_parts)),
                "sha256": source_sha,
                "existing_sha256": existing_sha,
                "status": status,
            }
        )

    if conflicts:
        raise ValidationError(
            "LUT library import would overwrite existing LUT files; pass --overwrite to replace them.",
            details={"conflicts": conflicts},
        )

    for entry in planned:
        if entry["status"] == "unchanged":
            continue
        try:
            os.makedirs(os.path.dirname(entry["target_path"]), exist_ok=True)
            shutil.copy2(entry["source_path"], entry["target_path"])
        except OSError as exc:
            raise APICallFailed(
                "Failed to copy LUT into DaVinci Resolve LUT library.",
                details={
                    "source_path": entry["source_path"],
                    "target_path": entry["target_path"],
                    "error": str(exc),
                },
            ) from exc

    verified: list[dict[str, Any]] = []
    verification_errors: list[dict[str, Any]] = []
    for entry in planned:
        target_path = entry["target_path"]
        exists = os.path.isfile(target_path)
        actual_sha = _file_sha256(target_path) if exists else None
        ok = exists and actual_sha == entry["sha256"]
        verified_entry = {
            **entry,
            "exists": exists,
            "verified_sha256": actual_sha,
            "verified": ok,
        }
        verified.append(verified_entry)
        if not ok:
            verification_errors.append(
                {
                    "target_path": target_path,
                    "expected_sha256": entry["sha256"],
                    "actual_sha256": actual_sha,
                    "exists": exists,
                }
            )

    if verification_errors:
        raise APICallFailed(
            "LUT library import failed file verification.",
            details={"verification_errors": verification_errors},
            recoverability="manual",
        )

    return {
        "source_path": source_root,
        "install_root": install_root,
        "install_root_kind": root_entry.get("kind"),
        "folder": library_folder,
        "installed_luts": verified,
        "imported_count": sum(1 for entry in verified if entry["status"] == "copied"),
        "unchanged_count": sum(1 for entry in verified if entry["status"] == "unchanged"),
        "lut_keys": [entry["lut_key"] for entry in verified],
    }


def _copy_lut_into_root(conn, source_path: str, root_entry: Dict[str, Any], *, ops_module) -> Dict[str, Any]:
    abs_source = os.path.abspath(os.path.expanduser(source_path))
    filename = os.path.basename(abs_source)
    if not filename:
        raise ValidationError("LUT path must point to a file.", details={"lut_path": source_path})

    root = os.path.abspath(os.path.expanduser(str(root_entry["root"])))
    target_dir = os.path.join(root, "CutAgent")
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as exc:
        raise APICallFailed(
            "Failed to create DaVinci Resolve LUT install folder.",
            details={
                "lut_path": source_path,
                "install_root": root,
                "install_root_kind": root_entry.get("kind"),
                "error": str(exc),
            },
        ) from exc

    target_path = os.path.join(target_dir, filename)
    target_matches_source = False

    if os.path.exists(target_path) and not os.path.samefile(abs_source, target_path):
        source_digest = _file_sha256(abs_source)
        target_digest = _file_sha256(target_path)
        target_matches_source = source_digest == target_digest
        if not target_matches_source:
            suffix = f"-{source_digest[:8]}"
            stem, ext = os.path.splitext(filename)
            target_path = os.path.join(target_dir, f"{stem}{suffix}{ext}")

    try:
        if not target_matches_source and (not os.path.exists(target_path) or not os.path.samefile(abs_source, target_path)):
            shutil.copy2(abs_source, target_path)
    except OSError as exc:
        raise APICallFailed(
            "Failed to copy LUT into DaVinci Resolve LUT folder.",
            details={
                "lut_path": source_path,
                "install_root": root,
                "install_root_kind": root_entry.get("kind"),
                "target_path": target_path,
                "error": str(exc),
            },
        ) from exc

    refresh_error = _refresh_lut_list_best_effort(conn, ops_module=ops_module)
    installed_key = _normalize_lut_key(os.path.join("CutAgent", os.path.basename(target_path)))
    return {
        "installed_lut_key": installed_key,
        "installed_lut_path": target_path,
        "install_root": root,
        "install_root_kind": root_entry.get("kind"),
        "refresh_error": refresh_error,
    }


def _install_lut_for_resolve(conn, source_path: str, *, ops_module) -> Tuple[str, str, Optional[str]]:
    root_candidates = _install_lut_root_candidates(ops_module=ops_module)
    if not root_candidates:
        raise APICallFailed(
            "No DaVinci Resolve LUT install root is available.",
            details={"lut_path": source_path, "resolve_lut_roots": _resolve_lut_roots(ops_module=ops_module)},
        )
    installed = _copy_lut_into_root(conn, source_path, root_candidates[0], ops_module=ops_module)
    return installed["installed_lut_key"], installed["installed_lut_path"], installed["refresh_error"]


def _install_strategy_for_roots(root_candidates: list[Dict[str, Any]], *, local_exists: bool) -> str:
    if not local_exists:
        return "direct_key_candidates"
    if any(root.get("kind") == "system" and root.get("writable") for root in root_candidates):
        return "prefer_system_root_with_user_fallback"
    if any(root.get("kind") == "user" for root in root_candidates):
        return "user_root_fallback_system_not_writable"
    return "no_writable_lut_root"


def _lut_path_candidates(conn, lut_path: str, *, ops_module) -> Dict[str, Any]:
    requested = str(lut_path).strip()
    if not requested:
        raise ValidationError("LUT path must not be empty.", details={"lut_path": lut_path})

    expanded = os.path.abspath(os.path.expanduser(requested))
    is_absolute_request = os.path.isabs(os.path.expanduser(requested))
    local_exists = os.path.isfile(expanded)
    if is_absolute_request and not local_exists:
        raise ValidationError(
            "LUT file not found.",
            details={"lut_path": lut_path, "resolved_path": expanded},
        )

    candidates = [requested, _normalize_lut_key(requested)]
    refresh_error = None
    candidate_records: list[Dict[str, Any]] = []
    relative_entry = None
    root_candidates: list[Dict[str, Any]] = []

    if local_exists:
        relative_entry = _relative_lut_entry_for_known_root(expanded, ops_module=ops_module)
        exclude_roots = {relative_entry["root_path"]} if relative_entry else set()
        root_candidates = _install_lut_root_candidates(ops_module=ops_module, exclude_roots=exclude_roots)
        if relative_entry:
            refresh_error = _refresh_lut_list_best_effort(conn, ops_module=ops_module)
            candidate_records.append(relative_entry)
        for root_entry in root_candidates:
            candidate_records.append(
                {
                    "source": "install",
                    "source_path": expanded,
                    "install_root": root_entry["root"],
                    "install_root_kind": root_entry["kind"],
                    "install_root_writable": root_entry.get("writable"),
                }
            )

    for candidate in _dedupe_strings(candidates):
        candidate_records.append({"source": "requested", "lut_path": candidate})

    return {
        "requested": requested,
        "local_path": expanded if local_exists else None,
        "local_file_exists": local_exists,
        "installed_lut_key": None,
        "installed_lut_path": None,
        "installed_luts": [],
        "refresh_error": refresh_error,
        "candidates": _dedupe_strings([record["lut_path"] for record in candidate_records if record.get("lut_path")]),
        "candidate_records": candidate_records,
        "resolve_lut_roots": _resolve_lut_roots(ops_module=ops_module),
        "install_strategy": _install_strategy_for_roots(root_candidates, local_exists=local_exists),
        "accepted_root": None,
        "accepted_root_path": None,
        "rejected_roots": [],
        "rejected_root_details": [],
    }


def _append_rejected_root(lut_info: Dict[str, Any], root_kind: Optional[str], root_path: Optional[str], lut_path: str, reason: str) -> None:
    if not root_kind:
        return
    if root_kind not in lut_info["rejected_roots"]:
        lut_info["rejected_roots"].append(root_kind)
    lut_info["rejected_root_details"].append(
        {
            "root": root_kind,
            "root_path": root_path,
            "lut_path": lut_path,
            "reason": reason,
        }
    )


def _readback_matches_candidate(
    readback: Any,
    candidate: str,
    lut_info: Dict[str, Any],
    record: Dict[str, Any],
    *,
    ops_module,
) -> bool:
    if readback is None:
        return True
    readback_norm = ops_module._normalize_lut_key(str(readback))
    if not readback_norm:
        return False

    acceptable = {candidate}
    acceptable.update(str(value) for value in lut_info.get("candidates", []) if value)
    acceptable.update(
        str(value)
        for value in [
            lut_info.get("requested"),
            lut_info.get("local_path"),
            lut_info.get("installed_lut_key"),
            lut_info.get("installed_lut_path"),
            record.get("installed_lut_key"),
            record.get("installed_lut_path"),
            record.get("lut_path"),
        ]
        if value
    )
    for installed in lut_info.get("installed_luts") or []:
        acceptable.update(
            str(value)
            for value in [installed.get("installed_lut_key"), installed.get("installed_lut_path")]
            if value
        )

    acceptable_norm = {ops_module._normalize_lut_key(value) for value in acceptable}
    if readback_norm in acceptable_norm:
        return True

    for value in acceptable_norm:
        if "/" in readback_norm and "/" in value and readback_norm.endswith(f"/{value}"):
            return True

    if "/" not in readback_norm:
        acceptable_names = {os.path.basename(value) for value in acceptable_norm}
        return readback_norm in acceptable_names
    return False


def _verify_lut_readback(getter, node_index: int, candidate: str, lut_info: Dict[str, Any], record: Dict[str, Any], *, ops_module) -> Dict[str, Any]:
    if not callable(getter):
        return {"readback_status": "not_available"}
    try:
        readback = getter(node_index)
    except Exception as exc:
        return {"readback_status": "error", "readback_error": str(exc)}
    matches = _readback_matches_candidate(readback, candidate, lut_info, record, ops_module=ops_module)
    return {
        "readback_status": "matched" if matches else "mismatch",
        "readback_lut_path": readback,
        "readback_match": matches,
    }


def _set_lut_with_candidates(conn, setter, node_index: int, lut_path: str, *, ops_module, getter=None) -> Tuple[str, Dict[str, Any]]:
    lut_info = _lut_path_candidates(conn, lut_path, ops_module=ops_module)
    attempts: list[Dict[str, Any]] = []
    last_exception: Optional[Exception] = None

    for record in lut_info["candidate_records"]:
        candidate = record.get("lut_path")
        root_kind = record.get("root_kind") or record.get("install_root_kind")
        root_path = record.get("root_path") or record.get("install_root")
        if record.get("source") == "install":
            try:
                installed = _copy_lut_into_root(
                    conn,
                    record["source_path"],
                    {"root": record["install_root"], "kind": record.get("install_root_kind")},
                    ops_module=ops_module,
                )
            except Exception as exc:
                last_exception = exc
                attempts.append(
                    {
                        "source": "install",
                        "root": root_kind,
                        "root_path": root_path,
                        "error": str(exc),
                    }
                )
                _append_rejected_root(lut_info, root_kind, root_path, "", f"install_error: {exc}")
                continue
            record.update(installed)
            candidate = installed["installed_lut_key"]
            root_kind = installed.get("install_root_kind")
            root_path = installed.get("install_root")
            lut_info["installed_luts"].append(installed)
            lut_info["installed_lut_key"] = lut_info["installed_lut_key"] or installed["installed_lut_key"]
            lut_info["installed_lut_path"] = lut_info["installed_lut_path"] or installed["installed_lut_path"]
            if installed.get("refresh_error"):
                lut_info["refresh_error"] = installed["refresh_error"]
            lut_info["candidates"] = _dedupe_strings([candidate, *lut_info.get("candidates", [])])

        if not candidate:
            continue
        attempt: Dict[str, Any] = {"lut_path": candidate, "source": record.get("source", "unknown")}
        if root_kind:
            attempt["root"] = root_kind
        if root_path:
            attempt["root_path"] = root_path
        try:
            result = setter(node_index, candidate)
        except Exception as exc:
            last_exception = exc
            attempt["error"] = str(exc)
            attempts.append(attempt)
            _append_rejected_root(lut_info, root_kind, root_path, candidate, f"set_exception: {exc}")
            continue
        attempt["result"] = bool(result)
        if not result:
            attempts.append(attempt)
            _append_rejected_root(lut_info, root_kind, root_path, candidate, "set_returned_false")
            continue

        readback_result = _verify_lut_readback(getter, node_index, candidate, lut_info, record, ops_module=ops_module)
        attempt.update(readback_result)
        attempts.append(attempt)
        if readback_result.get("readback_status") != "mismatch":
            lut_info["applied_lut_path"] = candidate
            lut_info["accepted_root"] = root_kind
            lut_info["accepted_root_path"] = root_path
            lut_info["attempts"] = attempts
            return candidate, lut_info
        _append_rejected_root(lut_info, root_kind, root_path, candidate, "readback_mismatch")

    lut_info["attempts"] = attempts
    message = "LUT file not found or not accepted by DaVinci Resolve."
    if last_exception is not None:
        message = f"{message} Last error: {last_exception}"
    raise APICallFailed(message, details=lut_info)


def get_lut_info(conn, clip_name: Optional[str], node: int, *, node_stack_layer_index: int = 1, ops_module) -> Dict[str, Any]:
    try:
        lut_path = (
            ops_module.get_node_lut(conn, clip_name, node)
            if node_stack_layer_index == 1
            else ops_module.get_node_lut(
                conn, clip_name, node, node_stack_layer_index=node_stack_layer_index
            )
        )
    except ClipNotFound:
        raise
    except Exception as exc:
        raise APICallFailed(
            "Failed to read LUT from node.",
            details={"clip": clip_name, "node": node, "error": str(exc)},
        ) from exc
    return {"node_stack_layer_index": node_stack_layer_index, "node": node, "lut_path": lut_path}


def set_lut(conn, clip_name: Optional[str], node: int, path: str, *, node_stack_layer_index: int = 1, ops_module) -> bool:
    if node_stack_layer_index != 1:
        return ops_module.set_node_lut(
            conn, clip_name, node, path, node_stack_layer_index=node_stack_layer_index
        )
    item = ops_module.resolve_item(conn, clip_name)
    setter = require_api_method(
        item,
        "SetLUT",
        capability_id="color.lut_set_clear",
        runtime_object="timeline_item",
    )
    getter = getattr(item, "GetLUT", None)
    if not callable(getter):
        def _node_graph_getter(node_index: int):
            return ops_module.get_node_lut(conn, clip_name, node_index)

        getter = _node_graph_getter
    try:
        ops_module._set_lut_with_candidates(conn, setter, node, path, getter=getter)
        return True
    except APICallFailed as exc:
        details = {"clip": clip_name, "node": node, "lut_path": path, **exc.details}
        raise APICallFailed("Failed to apply LUT. Check the file path and node index.", details=details) from exc


def clear_lut(conn, clip_name: Optional[str], node: int, *, node_stack_layer_index: int = 1, ops_module) -> bool:
    item = ops_module.resolve_item(conn, clip_name)
    target = item if node_stack_layer_index == 1 else ops_module._get_node_graph(
        conn, clip_name, node_stack_layer_index=node_stack_layer_index
    )
    result = target.SetLUT(node, "")
    if not result:
        raise APICallFailed("Failed to clear LUT.")

    getter = getattr(target, "GetLUT", None)
    if not callable(getter):
        def _node_graph_getter(node_index: int):
            return ops_module.get_node_lut(conn, clip_name, node_index, node_stack_layer_index=node_stack_layer_index)

        getter = _node_graph_getter

    try:
        readback_lut_path = getter(node)
    except Exception as exc:
        raise APICallFailed(
            "Cleared LUT, but readback failed.",
            details={"clip": clip_name, "node": node, "readback_status": "error", "readback_error": str(exc)},
        ) from exc
    if str(readback_lut_path or "").strip():
        raise APICallFailed(
            "Cleared LUT, but readback still reports a LUT on the target node.",
            details={
                "clip": clip_name,
                "node": node,
                "readback_status": "mismatch",
                "readback_lut_path": readback_lut_path,
            },
        )
    return True


def import_lut_library(
    conn,
    source_path: str,
    *,
    folder: str = "CutAgent/Imported",
    overwrite: bool = False,
    apply: bool = False,
    apply_clip_name: Optional[str] = None,
    apply_node: int = 1,
    apply_lut_key: Optional[str] = None,
    ops_module,
) -> Dict[str, Any]:
    if apply_node < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"node": apply_node, "minimum": 1},
            recoverability="not_applicable",
        )

    imported = _copy_lut_library_files(
        source_path,
        folder=folder,
        overwrite=overwrite,
        ops_module=ops_module,
    )
    refresh_error = _refresh_lut_list_best_effort(conn, ops_module=ops_module)
    refresh = {
        "method": "Project.RefreshLUTList",
        "status": "verified" if refresh_error is None else "warning",
        "error": refresh_error,
    }

    verification = {
        "status": "verified",
        "files_verified": True,
        "hashes_verified": True,
        "refresh": refresh,
    }
    result: Dict[str, Any] = {
        "route": "filesystem_api_lut_library_import",
        **imported,
        "refresh": refresh,
        "verification": verification,
    }

    requested_apply_key = str(apply_lut_key).strip() if apply_lut_key else None
    should_apply = apply or apply_clip_name is not None or requested_apply_key is not None
    if should_apply:
        lut_keys = imported["lut_keys"]
        selected_key = requested_apply_key or (lut_keys[0] if lut_keys else None)
        if not selected_key:
            raise APICallFailed(
                "LUT library import did not produce a LUT key to apply.",
                details={"source": source_path},
            )
        if requested_apply_key and requested_apply_key not in lut_keys:
            raise ValidationError(
                "--apply-lut must name a LUT imported by this command.",
                details={"apply_lut": requested_apply_key, "imported_lut_keys": lut_keys},
            )
        set_lut(conn, apply_clip_name, apply_node, selected_key, ops_module=ops_module)
        readback = get_lut_info(conn, apply_clip_name, apply_node, ops_module=ops_module)
        readback_lut = readback.get("lut_path")
        if not _readback_matches_candidate(
            readback_lut,
            selected_key,
            {"candidates": lut_keys, "installed_luts": imported["installed_luts"]},
            {"lut_path": selected_key},
            ops_module=ops_module,
        ):
            raise APICallFailed(
                "Imported LUT applied, but node readback did not match.",
                details={
                    "clip": apply_clip_name,
                    "node": apply_node,
                    "selected_lut_key": selected_key,
                    "readback_lut_path": readback_lut,
                },
            )
        result["applied"] = {
            "clip": apply_clip_name,
            "node": apply_node,
            "lut_key": selected_key,
            "readback": readback,
            "readback_lut_path": readback_lut,
            "verification": {"status": "verified"},
        }

    return result


def refresh_lut_list(conn) -> bool:
    try:
        result = conn.project.RefreshLUTList()
        if result:
            return True
    except (AttributeError, TypeError):
        pass
    raise APICallFailed("RefreshLUTList failed or not available in this DaVinci Resolve version.")
