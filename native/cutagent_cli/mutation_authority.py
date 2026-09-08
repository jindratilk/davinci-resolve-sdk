"""Private, compiled mutation-impact authority for the managed runtime.

This module is entered only through the native launcher. Release packaging
compiles it with the rest of CutAgent CLI; it is not a public command surface.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ._mutation_impact_registry import (
    PRIVATE_COMMAND_OPERATION_CLASS,
    PRIVATE_IMPACT_REGISTRY_DIGEST,
)

_ARG = "--cutagent-internal-mutation-impact"
_SECRET_ENV = "CUTAGENT_MUTATION_AUTHORITY_SECRET"
_PARENT_PID_ENV = "CUTAGENT_MUTATION_AUTHORITY_BRIDGE_PID"
_POLICY_SCOPE_VALID_ENV = "CUTAGENT_MUTATION_POLICY_SCOPE_VALID"
_CONTEXT = b"cutagent-mutation-impact-v1"
_NON_EDITING_LOCAL_UTILITY_COMMANDS = frozenset({
    "embedded.install",
    "embedded.start_server",
})


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not (float("-inf") < value < float("inf")):
            raise ValueError("Mutation impact numbers must be finite.")
        return 0 if value == 0 else value
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    raise ValueError("Mutation impact must be JSON-compatible.")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(_canonical(value), separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_bytes(value)).hexdigest()}"


def _option(args: list[str], name: str, fallback: str | None = None) -> str | None:
    for index in range(len(args) - 1, -1, -1):
        item = args[index]
        if item == name:
            return args[index + 1] if index + 1 < len(args) else fallback
        if item.startswith(f"{name}="):
            return item[len(name) + 1 :]
    return fallback


def _option_values(args: list[str], name: str) -> list[str | None]:
    values: list[str | None] = []
    index = 0
    while index < len(args):
        item = args[index]
        if item == name:
            values.append(args[index + 1] if index + 1 < len(args) else None)
            index += 2
            continue
        if item.startswith(f"{name}="):
            values.append(item[len(name) + 1 :])
        index += 1
    return values


def _read_payload(args: list[str], cwd: str | None) -> tuple[Any, str] | None:
    inline = _option(args, "--batch-json")
    if inline:
        return json.loads(inline), _digest(inline)
    fusion_index = args.index("fusion") if "fusion" in args else -1
    fusion_request = (
        args[fusion_index + 2]
        if "--sdk-graph-runtime" in args
        and fusion_index >= 0
        and fusion_index + 2 < len(args)
        and args[fusion_index + 1] == "apply"
        else None
    )
    requested = _option(args, "--batch") or _option(args, "--input") or _option(args, "--input-file") or fusion_request
    if not requested:
        return None
    if not cwd:
        raise ValueError("Referenced mutation payload requires an execution directory.")
    payload_path = (Path(cwd) / requested).resolve()
    raw = payload_path.read_bytes()
    return json.loads(raw.decode("utf-8")), f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _blade_effects(args: list[str], payload: Any, context: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = {
        "at": _option(args, "--at") or _option(args, "--record-frame"),
        "trackType": _option(args, "--track-type", "all"),
        "trackIndex": int(_option(args, "--track", "0") or "0"),
    }
    if payload is None:
        cuts = [defaults]
    else:
        raw = payload if isinstance(payload, list) else payload.get("cuts") if isinstance(payload, dict) else None
        if not isinstance(raw, list):
            raise ValueError("Blade batch impact is incomplete.")
        cuts = [{
            "at": entry.get("at", entry.get("record_frame", defaults["at"])),
            "trackType": entry.get("trackType", entry.get("track_type", defaults["trackType"])),
            "trackIndex": int(entry.get("trackIndex", entry.get("track", defaults["trackIndex"]))),
        } for entry in raw if isinstance(entry, dict)]
    if not cuts:
        raise ValueError("Blade impact contains no cuts.")
    targets = context.get("resolvedTargets") if isinstance(context.get("resolvedTargets"), list) else []
    effects = []
    for cut in cuts:
        track_type = cut["trackType"] if cut["trackType"] in {"video", "audio"} else None
        matching = [target for target in targets if isinstance(target, dict)
                    and target.get("trackType") == track_type
                    and (cut["trackIndex"] == 0 or target.get("trackIndex") == cut["trackIndex"])]
        complete = bool(track_type and cut["at"] is not None and matching)
        effects.append({
            "operation": "edit.blade",
            "kind": "blade",
            "trackTypes": [track_type] if track_type else ["video", "audio"],
            "targets": matching,
            "placementIntent": "marker" if context.get("placementIntent") == "marker" else "explicit",
            "broad": cut["trackType"] == "all" or cut["trackIndex"] == 0,
            "ambiguous": cut["at"] is None or not matching,
            "complete": complete,
        })
    return effects


def _is_reviewed_sdk_edit_preview(
    *, args: list[str], command_id: str, carrier: Any, context: dict[str, Any]
) -> bool:
    action = {
        "edit.insert": "insert",
        "edit.overwrite": "overwrite",
        "edit.trim": "trim",
    }.get(command_id)
    return bool(
        action
        and carrier == "sdk"
        and context.get("semanticReadOnlyPreview") == "timeline.edit.v1"
        and len(args) >= 4
        and args[:3] == ["-j", "edit", action]
        and args[-1] == "--dry-run"
        and args.count("--dry-run") == 1
    )


def lower_request(request: dict[str, Any]) -> dict[str, Any]:
    args = request.get("args")
    command_id = request.get("commandId")
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args) or not isinstance(command_id, str):
        raise ValueError("Mutation authority request is malformed.")
    context = request.get("policyContext") if isinstance(request.get("policyContext"), dict) else {}
    if _is_reviewed_sdk_edit_preview(
        args=args,
        command_id=command_id,
        carrier=request.get("carrier"),
        context=context,
    ):
        return {"classification": "read", "impact": None}
    operation_class = PRIVATE_COMMAND_OPERATION_CLASS.get(command_id)
    classification = "read" if operation_class == "read" else "mutation"
    if classification == "read":
        return {"classification": "read", "impact": None}

    try:
        payload_result = _read_payload(args, request.get("cwd"))
        payload, payload_digest = payload_result if payload_result else (None, None)
    except Exception:
        payload, payload_digest = None, None
        payload_result = "invalid"
    minimum_binding = "project+timeline"
    effects: list[dict[str, Any]] = []
    if command_id in {"edit.blade", "edit.split"} and payload_result != "invalid":
        try:
            effects = _blade_effects(args, payload, context)
        except Exception:
            effects = [{
                "operation": "edit.blade", "kind": "unknown", "trackTypes": [], "targets": [],
                "placementIntent": "unknown", "broad": False, "ambiguous": True, "complete": False,
            }]
    elif command_id == "project.create":
        minimum_binding = "account/project-library"
        targets = ([{"kind": "project_library", "stableId": context["projectLibraryId"],
                     "revision": context["projectLibraryRevision"]}]
                   if context.get("projectLibraryId") and context.get("projectLibraryRevision") else [])
        effects = [{"operation": command_id, "kind": "create", "trackTypes": [], "targets": targets,
                    "placementIntent": "explicit", "broad": False, "ambiguous": len(targets) != 1,
                    "complete": len(targets) == 1}]
    elif command_id == "timeline.create":
        minimum_binding = "project"
        targets = ([{"kind": "project", "stableId": context["projectId"], "revision": context["projectRevision"]}]
                   if context.get("projectId") and context.get("projectRevision") else [])
        effects = [{"operation": command_id, "kind": "create", "trackTypes": [], "targets": targets,
                    "placementIntent": "explicit", "broad": False, "ambiguous": len(targets) != 1,
                    "complete": len(targets) == 1}]
    elif (command_id in {"version.create", "version.restore"}
          and context.get("workflowCheckpointAuthority") == "sdk_workflow_v1"):
        guarded_restore = (command_id != "version.restore" or (
            isinstance(context.get("expectedCurrentStateHash"), str)
            and len(context["expectedCurrentStateHash"]) == 71
            and context["expectedCurrentStateHash"].startswith("sha256:")
            and context.get("projectRevision") == context.get("expectedCurrentStateHash")
        ))
        targets = ([
            *([{"kind": "project", "stableId": context["projectId"],
                "revision": context["expectedCurrentStateHash"]}]
              if command_id == "version.restore" and context.get("projectId")
              and context.get("expectedCurrentStateHash") else []),
            {"kind": "timeline", "stableId": context["timelineId"],
             "revision": context["timelineRevision"]},
        ] if context.get("timelineId") and context.get("timelineRevision") else [])
        expected_targets = 2 if command_id == "version.restore" else 1
        effects = [{"operation": command_id,
                    "kind": "create" if command_id == "version.create" else "update",
                    "trackTypes": [], "targets": targets, "placementIntent": "explicit",
                    "broad": False, "ambiguous": len(targets) != expected_targets,
                    "complete": len(targets) == expected_targets and guarded_restore}]
    elif command_id == "media.import":
        minimum_binding = "project"
        targets = ([{"kind": "project", "stableId": context["projectId"], "revision": context["projectRevision"]}]
                   if context.get("projectId") and context.get("projectRevision") else [])
        effects = [{"operation": command_id, "kind": "create", "trackTypes": [], "targets": targets,
                    "placementIntent": "explicit", "broad": False, "ambiguous": len(targets) != 1,
                    "complete": len(targets) == 1}]
    elif command_id in {"timeline.marker.add", "timeline.marker.update", "timeline.marker.delete"}:
        kind = "create" if command_id.endswith(".add") else "update" if command_id.endswith(".update") else "delete"
        targets = context.get("resolvedTargets") if isinstance(context.get("resolvedTargets"), list) else []
        effects = [{"operation": command_id, "kind": kind, "trackTypes": [], "targets": targets,
                    "placementIntent": "marker", "broad": False, "ambiguous": len(targets) != 1,
                    "complete": len(targets) == 1}]
    elif command_id in {
        "color.page.primary_set",
        "color.page.node_add",
        "color.node.label_set",
        "color.grade_apply",
        "color.page.resolvefx_add",
    }:
        targets = [
            target for target in context.get("resolvedTargets", [])
            if isinstance(target, dict)
            and target.get("kind") == "clip"
            and target.get("trackType") == "video"
        ]
        effects = [{"operation": command_id, "kind": "update", "trackTypes": ["video"], "targets": targets,
                    "placementIntent": "explicit", "broad": False, "ambiguous": len(targets) != 1,
                    "complete": len(targets) == 1}]
    elif command_id == "timeline.items.delete" and context.get("semanticOperation") == "clip_remove":
        targets = [target for target in context.get("resolvedTargets", [])
                   if isinstance(target, dict) and target.get("kind") in {"timeline", "clip", "track"}]
        timelines = [target for target in targets if target.get("kind") == "timeline"]
        clips = [target for target in targets if target.get("kind") == "clip"]
        tracks = [target for target in targets if target.get("kind") == "track"]
        def valid_coordinate(target: dict[str, Any]) -> bool:
            return (target.get("trackType") in {"video", "audio"}
                    and isinstance(target.get("trackIndex"), int)
                    and not isinstance(target.get("trackIndex"), bool)
                    and target["trackIndex"] >= 1)
        def coordinate(target: dict[str, Any]) -> tuple[Any, Any]:
            return target.get("trackType"), target.get("trackIndex")
        selector_item_ids = context.get("selectorItemIds") if isinstance(context.get("selectorItemIds"), list) else []
        transition_item_ids = context.get("expectedLinkTransitionIds") if isinstance(context.get("expectedLinkTransitionIds"), list) else []
        selector_clips = [clip for clip in clips if clip.get("stableId") in selector_item_ids]
        transition_clips = [clip for clip in clips if clip.get("stableId") in transition_item_ids]
        selector_clip_coordinates = {coordinate(target) for target in selector_clips}
        track_coordinates = {coordinate(target) for target in tracks}
        track_type_args = _option_values(args, "--track-type")
        track_index_args = _option_values(args, "--track")
        start_args = _option_values(args, "--start-frame")
        end_args = _option_values(args, "--end-frame")
        match_args = _option_values(args, "--match")
        try:
            selector_track_index = int(track_index_args[0]) if len(track_index_args) == 1 else None
        except (TypeError, ValueError):
            selector_track_index = None
        selector_range = context.get("selectorRange") if isinstance(context.get("selectorRange"), dict) else {}
        selector_coordinate = (track_type_args[0], selector_track_index) if len(track_type_args) == 1 else None
        exact_selector = (len(track_type_args) == 1 and track_type_args[0] in {"video", "audio"}
                          and len(track_index_args) == 1 and isinstance(selector_track_index, int) and selector_track_index >= 1
                          and start_args == [f'{selector_range.get("start")}f']
                          and end_args == [f'{selector_range.get("endExclusive")}f']
                          and match_args == ["contained"]
                          and len(selector_clip_coordinates) == 1 and selector_coordinate in selector_clip_coordinates
                          and len(track_coordinates) == 1 and selector_coordinate in track_coordinates)
        track_types = sorted({target.get("trackType") for target in [*clips, *tracks] if target.get("trackType")})
        exact = (len(targets) == len(context.get("resolvedTargets", [])) and len(timelines) == 1
                 and bool(selector_clips) and bool(tracks)
                 and all(valid_coordinate(target) for target in [*clips, *tracks])
                 and len({(target.get("kind"), target.get("stableId")) for target in targets}) == len(targets)
                 and len(set([*selector_item_ids, *transition_item_ids])) == len(selector_item_ids) + len(transition_item_ids)
                 and len(selector_clips) == len(selector_item_ids)
                 and len(transition_clips) == len(transition_item_ids)
                 and len(clips) == len(selector_clips) + len(transition_clips)
                 and selector_clip_coordinates == track_coordinates
                 and len(track_coordinates) == len(tracks)
                 and exact_selector)
        selector_broad = (len(track_type_args) != 1 or (track_type_args and track_type_args[0] == "all")
                          or len(track_index_args) != 1 or selector_track_index == 0 or len(track_coordinates) != 1)
        effects = [{"operation": command_id, "kind": "delete", "trackTypes": track_types, "targets": targets,
                    "placementIntent": "explicit", "broad": selector_broad, "ambiguous": not exact, "complete": exact}]
    elif command_id == "fusion.apply" and "--sdk-graph-runtime" in args and payload_result != "invalid":
        targets = context.get("resolvedTargets") if isinstance(context.get("resolvedTargets"), list) else []
        target_kinds = {target.get("kind") for target in targets if isinstance(target, dict)}
        exact_targets = targets if len(targets) == 2 and target_kinds == {"clip", "fusion_composition"} else []
        effects = [{
            "operation": "fusion.apply", "kind": "update", "trackTypes": ["video"],
            "targets": exact_targets, "placementIntent": "explicit", "broad": False,
            "ambiguous": len(exact_targets) != 2, "complete": len(exact_targets) == 2,
        }]

    complete = bool(effects) and all(effect["complete"] for effect in effects)
    ambiguous = not effects or any(effect["ambiguous"] for effect in effects)
    broad = any(effect["broad"] for effect in effects)
    impact = {
        "contractVersion": 1,
        "carrier": request.get("carrier", "cli"),
        "status": "mutation" if operation_class else "unknown",
        "minimumBinding": minimum_binding,
        "registryDigest": PRIVATE_IMPACT_REGISTRY_DIGEST,
        "canonicalRequestDigest": _digest({"commandId": command_id, "args": args}),
        "referencedPayloadDigests": ([context["expectedCurrentStateHash"]]
                                      if command_id == "version.restore"
                                      and context.get("workflowCheckpointAuthority") == "sdk_workflow_v1"
                                      and isinstance(context.get("expectedCurrentStateHash"), str)
                                      and len(context["expectedCurrentStateHash"]) == 71
                                      and context["expectedCurrentStateHash"].startswith("sha256:")
                                      else [payload_digest] if payload_digest else []),
        "requestId": context.get("requestId"), "operationId": context.get("operationId"),
        "executionId": context.get("executionId"), "scopeId": context.get("scopeId"),
        "scopeRevision": context.get("scopeRevision"), "projectLibraryId": context.get("projectLibraryId"),
        "effects": effects, "closedComposition": context.get("closedComposition") is True,
        "complete": complete, "ambiguous": ambiguous, "broad": broad,
        "executableStableTargetPrecondition": context.get("executableStableTargetPrecondition") is True,
        "verificationPolicy": {"minimumEvidence": (
                                   ["readback", "structural", "rendered", "visual"]
                                   if command_id == "fusion.apply" and "--sdk-graph-runtime" in args
                                   else ["readback", "structural"]
                               ),
                               "requireProtectedStatePreserved": True,
                               "protectedTargetEvidence": "every_declared_target"},
    }
    for key in ("projectId", "timelineId", "projectRevision", "timelineRevision"):
        if context.get(key):
            impact[key] = context[key]
    return {"classification": classification, "impact": impact}


def handle_internal_request(argv: list[str]) -> bool:
    if not argv or argv[0] != _ARG:
        return False
    if len(argv) != 2:
        raise SystemExit(2)
    secret = os.environ.get(_SECRET_ENV, "")
    expected_parent = os.environ.get(_PARENT_PID_ENV, "")
    if len(secret) < 43 or not expected_parent.isdigit() or os.getppid() != int(expected_parent):
        raise SystemExit(2)
    try:
        request_bytes = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
        if len(request_bytes) > 8 * 1024 * 1024:
            raise ValueError
        request = json.loads(request_bytes)
        if not isinstance(request, dict) or request.get("nonce") != argv[1]:
            raise ValueError
        result = lower_request(request)
        artifact = {"schemaVersion": 1, "nonce": argv[1], "registryDigest": PRIVATE_IMPACT_REGISTRY_DIGEST,
                    **result}
        signature = hmac.new(secret.encode(), _CONTEXT + b"\0" + _canonical_bytes(artifact), hashlib.sha256).hexdigest()
        print(json.dumps({"artifact": artifact, "signature": signature}, separators=(",", ":")))
        return True
    except Exception:
        raise SystemExit(2) from None


def _macos_process_path(pid: int) -> Path | None:
    try:
        import ctypes

        library = ctypes.CDLL("/usr/lib/libproc.dylib")
        buffer = ctypes.create_string_buffer(4096)
        length = library.proc_pidpath(pid, buffer, len(buffer))
        return Path(os.fsdecode(buffer.raw[:length])).resolve() if length > 0 else None
    except Exception:
        return None


def _macos_parent_pid(pid: int) -> int | None:
    try:
        result = subprocess.run(
            ["/bin/ps", "-o", "ppid=", "-p", str(pid)],
            check=True,
            capture_output=True,
            text=True,
            env={},
            timeout=1,
        )
        return int(result.stdout.strip())
    except Exception:
        return None


def _windows_process_entry(pid: int) -> tuple[int, Path] | None:
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot in (0, ctypes.c_void_p(-1).value):
            return None
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found_parent = None
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.th32ProcessID == pid:
                found_parent = int(entry.th32ParentProcessID)
                break
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        kernel32.CloseHandle(snapshot)
        if found_parent is None:
            return None
        process = kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return None
        buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(buffer))
        ok = kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(length))
        kernel32.CloseHandle(process)
        return (found_parent, Path(buffer.value).resolve()) if ok else None
    except Exception:
        return None


def _trusted_packaged_bridge_parent(*args, **kwargs):
    return __import__("cutagent_cli.local_admission", fromlist=["validate_local_command"]).validate_local_command()


def require_mutation_execution_scope(command_id: str, *, authorization_is_required: bool = True) -> None:
    """Fail closed when a packaged mutation did not consume bridge policy."""
    if not authorization_is_required:
        return
    operation_class = PRIVATE_COMMAND_OPERATION_CLASS.get(command_id)
    if operation_class == "read" or command_id in _NON_EDITING_LOCAL_UTILITY_COMMANDS:
        return
    if os.environ.get(_POLICY_SCOPE_VALID_ENV) != "1" or not _trusted_packaged_bridge_parent():
        from .errors import AuthRequired

        raise AuthRequired(
            "A current CutAgent editing-constraint decision is required for this mutation."
        )
