"""Concrete prepared-action descriptors for safe project and render mutations.

The descriptors in this module bind fixed typed action identities to existing
CutAgent CLI semantic owners.  No caller supplies command names, argv, native
method names, or lowering metadata.  Every mutation snapshots the active
project before execution, verifies native readback, and reports compensation
truthfully when an exact restoration cannot be proved.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Callable, Mapping
import xml.etree.ElementTree as ET

from ..connection import get_connection
from ..core import project_ops, render_engine
from ..core.sdk_live_inspection import documented_unique_id
from ..errors import APICallFailed, ValidationError


_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_PROJECT_ID = re.compile(r"^project_[A-Za-z0-9][A-Za-z0-9._~-]*$")
_REVISION = re.compile(r"^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$")
_NUMERIC_PROJECT_SETTING_KEYS = frozenset(
    {"superScale", "timelineFrameRate", "timelinePlaybackFrameRate"}
)
_PRIVATE_PUBLIC_KEYS = frozenset(
    {"argv", "commandId", "commandPath", "engine", "lowering", "preState", "recoveryPlan"}
)


_CAPABILITY_IDS = {
    "cutagent.action.project.rename": "project.settings_write",
    "cutagent.action.project.settings_set": "project.settings_write",
    "cutagent.action.render.alpha": "render.settings_write",
    "cutagent.action.render.archive_settings": "render.archive_settings",
    "cutagent.action.render.delete": "render.queue_delete",
    "cutagent.action.render.encoding": "render.settings_write",
    "cutagent.action.render.mode.set": "render.mode_set",
    "cutagent.action.render.preset_delete": "render.preset_save",
    "cutagent.action.render.preset_load": "render.preset_load",
    "cutagent.action.render.preset_save": "render.preset_save",
    "cutagent.action.render.settings_set": "render.settings_write",
    "cutagent.action.render.subtitles": "render.settings_write",
}


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 9_007_199_254_740_991:
            raise ValidationError("Prepared action integer exceeds the canonical JSON range.")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError("Prepared action number must be finite.")
        return 0 if value == 0 else value
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    raise ValidationError("Prepared action value must be canonical JSON.")


def _digest(value: Any) -> str:
    raw = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"


def _revision(value: Any) -> str:
    return f"revision_{_digest(value)[7:]}"


def _project_setting_number(key: str, value: Any) -> Decimal | None:
    if key not in _NUMERIC_PROJECT_SETTING_KEYS or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, float)):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _project_setting_values_match(key: str, actual: Any, expected: Any) -> bool:
    actual_number = _project_setting_number(key, actual)
    expected_number = _project_setting_number(key, expected)
    if actual_number is not None or expected_number is not None:
        return actual_number is not None and expected_number is not None and actual_number == expected_number
    return isinstance(actual, str) and isinstance(expected, str) and actual == expected


def _project_setting_string(key: str, value: Any) -> str | None:
    if value is None:
        return None
    number = _project_setting_number(key, value)
    if number is not None:
        return str(value).strip()
    return value if isinstance(value, str) else str(value)


def _project_setting_public_values(
    key: str, requested: Any, applied: Any, previous: Any
) -> tuple[str, str, str | None]:
    requested_text = _project_setting_string(key, requested)
    applied_text = _project_setting_string(key, applied)
    previous_text = _project_setting_string(key, previous)
    if key != "perfCacheClipsLocation":
        return requested_text, applied_text, previous_text
    current_token = "[redacted]"
    previous_token = (
        None
        if previous_text is None
        else current_token
        if _project_setting_values_match(key, previous, applied)
        else "[redacted-previous]"
    )
    return current_token, current_token, previous_token


def _project_setting_runtime_value(key: str, value: Any) -> str | None:
    if key in _NUMERIC_PROJECT_SETTING_KEYS:
        number = _project_setting_number(key, value)
        if number is None:
            return None
        if number == 0:
            return "0"
        return format(number.normalize(), "f")
    return value if isinstance(value, str) else None


def _project_binding(context: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    project = context.get("project")
    exact = context.get("exactRequestBinding")
    mutation_base = context.get("mutationBase")
    if isinstance(exact, Mapping) and isinstance(mutation_base, Mapping):
        identities = exact.get("identities")
        revisions = exact.get("revisions")
        runtime_project = project if isinstance(project, Mapping) else {}
        if isinstance(identities, Mapping) and isinstance(revisions, Mapping):
            project = {
                "projectLibraryId": identities.get("projectLibraryId"),
                "projectId": identities.get("projectId"),
                "projectRevision": revisions.get("project"),
                **{
                    key: runtime_project[key]
                    for key in ("nativeProjectId", "nativeProjectLibrary", "nativeRenderJobs")
                    if key in runtime_project
                },
            }
    if not isinstance(project, Mapping):
        raise ValidationError("Prepared project mutation requires signed project context.")
    required_project = ("projectLibraryId", "projectId", "projectRevision")
    if any(not isinstance(project.get(key), str) or not project[key] for key in required_project):
        raise ValidationError("Prepared project mutation has an incomplete project binding.")
    return dict(project), {}


def _target(context: Mapping[str, Any]) -> dict[str, Any]:
    project, _ = _project_binding(context)
    return {
        "kind": "project",
        "stableId": project["projectId"],
        "revision": project["projectRevision"],
    }


def _impact(context: Mapping[str, Any], action_id: str, value: Mapping[str, Any]) -> dict[str, Any]:
    project, _ = _project_binding(context)
    mutation_base = context.get("mutationBase")
    if not isinstance(mutation_base, Mapping):
        raise ValidationError("Prepared project mutation has no carrier-owned mutation base.")
    required_base = {
        "contractVersion", "carrier", "minimumBinding", "registryDigest",
        "canonicalRequestDigest", "referencedPayloadDigests", "requestId",
        "operationId", "executionId",
        "projectLibraryId",
    }
    project_open = action_id == "cutagent.action.project.open"
    if not project_open:
        required_base.update({"projectId", "projectRevision"})
    if not required_base.issubset(mutation_base):
        raise ValidationError("Prepared project mutation has an incomplete carrier-owned mutation base.")
    project_binding_fields = {"projectId", "projectRevision"}
    has_project_binding = project_binding_fields.issubset(mutation_base)
    has_partial_project_binding = bool(project_binding_fields.intersection(mutation_base)) and not has_project_binding
    if (
        mutation_base.get("projectLibraryId") != project["projectLibraryId"]
        or (project_open and has_partial_project_binding)
        or (project_open and not has_project_binding and mutation_base.get("minimumBinding") != "account/project-library")
        or (not project_open and mutation_base.get("projectId") != project["projectId"])
        or (not project_open and mutation_base.get("projectRevision") != project["projectRevision"])
        or (project_open and has_project_binding and mutation_base.get("projectId") != project["projectId"])
        or (project_open and has_project_binding and mutation_base.get("projectRevision") != project["projectRevision"])
    ):
        raise ValidationError("Prepared project mutation carrier binding drifted.")
    return {
        **dict(mutation_base),
        "status": "mutation",
        "effects": [{
            "operation": action_id.removeprefix("cutagent.action."),
            "kind": "update",
            "trackTypes": [],
            "targets": [_target(context)],
            "placementIntent": "explicit",
            "broad": False,
            "ambiguous": False,
            "complete": True,
        }],
        "closedComposition": True,
        "complete": True,
        "ambiguous": False,
        "broad": False,
        "executableStableTargetPrecondition": True,
        "verificationPolicy": {
            "minimumEvidence": ["readback", "structural"],
            "requireProtectedStatePreserved": True,
            "protectedTargetEvidence": "every_declared_target",
        },
    }


def _evidence(action_id: str, state: Any) -> list[dict[str, Any]]:
    digest = _digest(state)
    return [
        {"modality": "readback", "digest": digest, "summary": f"{action_id} native readback matched."},
        {"modality": "structural", "digest": digest, "summary": "The bound project identity and protected context were preserved."},
    ]


def _assert_public(value: Any) -> Any:
    normalized = _canonical(value)

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            if _PRIVATE_PUBLIC_KEYS.intersection(item):
                raise ValidationError("Private descriptor state reached the public result.")
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(normalized)
    return normalized


def _native_library_identity(conn: Any) -> dict[str, str] | None:
    getter = getattr(getattr(conn, "project_manager", None), "GetCurrentDatabase", None)
    database = getter() if callable(getter) else None
    if not isinstance(database, Mapping):
        return None
    name = database.get("DbName")
    kind = database.get("DbType")
    if not isinstance(name, str) or not name.strip() or not isinstance(kind, str):
        return None
    normalized_kind = kind.strip().lower()
    if normalized_kind not in {"disk", "postgresql"}:
        return None
    identity = {"name": name.strip(), "kind": normalized_kind}
    if normalized_kind == "postgresql":
        address = database.get("IpAddress")
        if not isinstance(address, str) or not address.strip():
            return None
        identity["address"] = address.strip()
    return identity


def _assert_native_project_binding(context: Mapping[str, Any], conn: Any) -> dict[str, Any]:
    project, _ = _project_binding(context)
    native_project_id = project.get("nativeProjectId")
    native_library = project.get("nativeProjectLibrary")
    if (
        not isinstance(native_project_id, str)
        or not native_project_id
        or not isinstance(native_library, Mapping)
    ):
        raise ValidationError("Prepared project mutation omitted its private native execution binding.")
    expected_library_keys = (
        {"name", "kind", "address"}
        if native_library.get("kind") == "postgresql"
        else {"name", "kind"}
    )
    if (
        set(native_library) != expected_library_keys
        or any(not isinstance(native_library.get(key), str) or not native_library[key]
               for key in expected_library_keys)
    ):
        raise ValidationError("Prepared project mutation has a malformed native library binding.")
    actual_project_id = documented_unique_id(conn.project)
    actual_library = _native_library_identity(conn)
    if actual_project_id != native_project_id or actual_library != dict(native_library):
        raise ValidationError("The exact current DaVinci Resolve project or project library changed.")
    return {
        "projectId": project["projectId"],
        "nativeProjectId": actual_project_id,
        "projectLibraryId": project["projectLibraryId"],
        "nativeProjectLibrary": actual_library,
    }


def _project_protected_state(conn: Any, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    project = conn.project
    timeline = getattr(conn, "timeline", None)
    jobs = project.GetRenderJobList() if callable(getattr(project, "GetRenderJobList", None)) else []
    return {
        "binding": (
            _assert_native_project_binding(context, conn)
            if context is not None
            else {
                "nativeProjectId": documented_unique_id(conn.project),
                "nativeProjectLibrary": _native_library_identity(conn),
            }
        ),
        "projectName": project.GetName(),
        "timelineName": timeline.GetName() if timeline is not None and callable(getattr(timeline, "GetName", None)) else None,
        "renderJobIds": sorted(
            str(job.get("JobId")) for job in (jobs or [])
            if isinstance(job, Mapping) and job.get("JobId") is not None
        ),
    }


def _preset_settings_projection(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Decode the bounded Deliver fields used by the typed render actions."""
    try:
        root = ET.fromstring(str(snapshot["canonical_xml"]))
        blobs = list(root.iter("FieldsBlob"))
        if len(blobs) != 1 or not blobs[0].text:
            raise ValueError("missing FieldsBlob")
        from ..core.fairlight_ops import _decode_bmd_fields_blob_entries

        version, entries = _decode_bmd_fields_blob_entries(bytes.fromhex(blobs[0].text))
        if version != 1:
            raise ValueError("unsupported FieldsBlob version")
        fields = {entry["key"]: entry for entry in entries}
        extras = {
            element.findtext("DbKey"): element.findtext("DbVal")
            for element in root.findall(".//ExtraInfoMap/Element")
            if element.findtext("DbKey")
        }

        def flag(key: str) -> bool | None:
            entry = fields.get(key)
            if not isinstance(entry, Mapping) or entry.get("value_type") != 1:
                return None
            raw = entry.get("value_raw")
            if raw not in (b"\x00\x00", b"\x00\x01"):
                return None
            return raw == b"\x00\x01"

        def integer(key: str) -> int | None:
            entry = fields.get(key)
            if not isinstance(entry, Mapping) or entry.get("value_type") not in {2, 3}:
                return None
            raw = entry.get("value_raw")
            if not isinstance(raw, bytes) or len(raw) != 5 or raw[0] != 0:
                return None
            return int.from_bytes(raw[1:], byteorder="big", signed=True)

        subtitle_format = {
            1: "BurnIn",
            3: "EmbeddedCaptions",
        }.get(integer("SubtitleRecordType"))
        if subtitle_format is None and fields.get("SubtitleRecordCodec") is not None:
            subtitle_format = "SeparateFile"
        projected = {
            "__presetSha256": snapshot["canonical_xml_sha256"],
            "__fields": {key: {"type": item["value_type"], "raw": item["value_raw"].hex()} for key, item in sorted(fields.items())},
            "__extra": dict(sorted(extras.items())),
        }
        alpha = flag("RecordWithAlpha")
        premultiplied = flag("IsRecordAlphaPremult")
        subtitles = flag("RecordSubtitleEnabled")
        if alpha is not None:
            projected["ExportAlpha"] = alpha
        if alpha is not None:
            projected["AlphaMode"] = "premultiplied" if premultiplied is True else "straight"
        if subtitles is not None:
            projected["ExportSubtitle"] = subtitles
        if subtitle_format is not None:
            projected["SubtitleFormat"] = subtitle_format
        if extras.get("network_optimization") in {"0", "1"}:
            projected["NetworkOptimization"] = extras["network_optimization"] == "1"
        encoding_profile = {"66": "Baseline", "77": "Main", "100": "High"}.get(
            extras.get("h264_profile")
        )
        if encoding_profile is not None:
            projected["EncodingProfile"] = encoding_profile
        if extras.get("h264_passes") in {"1", "2"}:
            projected["MultiPassEncode"] = extras["h264_passes"] == "2"
        return projected
    except Exception as exc:
        raise APICallFailed("DaVinci Resolve exported an undecodable render-settings snapshot.") from exc


def _capture_render_snapshot(conn: Any, context: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    custody = render_engine._snapshot_render_context(conn)
    try:
        if custody.get("custody") == "render_preset_export":
            settings = _preset_settings_projection(custody)
            format_codec = {"format": custody["format"], "codec": custody["codec"]}
            mode = custody["render_mode"]
        else:
            settings = custody.get("settings")
            format_codec = {"format": custody.get("format"), "codec": custody.get("codec")}
            mode = custody.get("render_mode")
        if not isinstance(settings, Mapping) or not all(isinstance(format_codec.get(key), str) and format_codec[key] for key in ("format", "codec")) or mode not in {0, 1}:
            raise APICallFailed("DaVinci Resolve did not expose a complete render-settings snapshot.")
        return ({
            "settings": _canonical(settings),
            "formatCodec": _canonical(format_codec),
            "mode": mode,
            "protected": _project_protected_state(conn, context),
        }, dict(custody))
    except Exception:
        if custody.get("custody") == "render_preset_export":
            render_engine._discard_render_context_preset_snapshot(conn, dict(custody))
        raise


def _release_render_snapshot(conn: Any, custody: Mapping[str, Any]) -> None:
    if custody.get("custody") == "render_preset_export":
        render_engine._discard_render_context_preset_snapshot(conn, dict(custody))


def _restore_render_snapshot(conn: Any, context: Mapping[str, Any], before: Mapping[str, Any], custody: Mapping[str, Any]) -> bool:
    try:
        _assert_native_project_binding(context, conn)
        render_engine._restore_render_context(conn, dict(custody))
        return _project_protected_state(conn, context) == before.get("protected")
    except Exception:
        return False


def _valid_completed_project_payload(
    payload: Any,
    *,
    target_keys: set[str],
    data_keys: set[str],
    evidence_kind: str,
) -> bool:
    if not isinstance(payload, Mapping) or set(payload) != {
        "status", "changed", "target", "data", "verification", "recovery",
    }:
        return False
    target = payload.get("target")
    data = payload.get("data")
    verification = payload.get("verification")
    recovery = payload.get("recovery")
    if (
        payload.get("status") != "completed"
        or not isinstance(payload.get("changed"), bool)
        or not isinstance(target, Mapping)
        or set(target) != target_keys
        or not isinstance(data, Mapping)
        or set(data) != data_keys
        or not isinstance(verification, Mapping)
        or set(verification) != {"outcome", "evidence", "protectedState"}
        or verification.get("outcome") != "passed"
        or verification.get("protectedState") != "preserved"
        or not isinstance(recovery, Mapping)
        or set(recovery) != {"state", "retry", "guidance"}
        or recovery.get("state") != "not_needed"
        or recovery.get("retry") != "safe"
        or not isinstance(recovery.get("guidance"), str)
        or not 1 <= len(recovery["guidance"]) <= 500
    ):
        return False
    evidence = verification.get("evidence")
    return (
        isinstance(evidence, list)
        and 1 <= len(evidence) <= 32
        and any(item.get("kind") == evidence_kind for item in evidence if isinstance(item, Mapping))
        and all(
            isinstance(item, Mapping)
            and set(item) == {"kind", "summary"}
            and item.get("kind") in {
                "structural_readback", "artifact_readback", "context_readback",
                "checkpoint_readback", "manual_review",
            }
            and isinstance(item.get("summary"), str)
            and 1 <= len(item["summary"]) <= 500
            for item in evidence
        )
    )


@dataclass(frozen=True)
class ProjectRenameDescriptor:
    operation_class = "mutation"
    version = 1
    action_id = "cutagent.action.project.rename"
    capability_id = _CAPABILITY_IDS[action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != {"name"} or not isinstance(value["name"], str):
            raise ValidationError("Project rename input must contain only name.")
        name = value["name"].strip()
        if not name or len(name) > 1024:
            raise ValidationError("Project name must contain between 1 and 1024 characters.")
        project_ops.validate_project_name(name)
        return {"name": name}

    def _snapshot(self, context: Mapping[str, Any]) -> dict[str, Any]:
        conn = get_connection(require_project=True)
        return {"name": conn.project.GetName(), "protected": _project_protected_state(conn, context)}

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        before = self._snapshot(context)
        return {"targets": [_target(context)], "preState": before, "impact": _impact(context, self.action_id, value),
                "lowering": {"name": value["name"]}, "verification": {"minimumEvidence": ["readback", "structural"]},
                "recovery": {"strategy": "restore_previous_project_name"}}

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        return {"targets": [_target(context)], "preState": self._snapshot(context)}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        conn = get_connection(require_project=True)
        _assert_native_project_binding(context, conn)
        return project_ops.rename_current_project(conn, prepared["lowering"]["name"])

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        current = self._snapshot(context)
        expected = prepared["lowering"]["name"]
        protected = {**prepared["preState"]["protected"], "projectName": expected}
        passed = current["name"] == expected and current["protected"] == protected
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, current),
                "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        try:
            conn = get_connection(require_project=True)
            _assert_native_project_binding(context, conn)
            project_ops.rename_current_project(conn, prepared["preState"]["name"])
            restored = self._snapshot(context) == prepared["preState"]
        except Exception:
            restored = False
        return {"outcome": "succeeded" if restored else "manual_required", "attempted": True,
                "manualActionRequired": not restored}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        project, _ = _project_binding(context)
        old = prepared["preState"]["name"]
        new = prepared["lowering"]["name"]
        return _assert_public({"actionId": self.action_id, "payload": {"status": "completed", "changed": old != new,
            "target": {"id": project["projectId"], "name": new}, "data": {"previousName": old, "currentName": new},
            "verification": {"outcome": "passed", "evidence": [{"kind": "context_readback", "summary": "Active project name matched."}], "protectedState": "preserved"},
            "recovery": {"state": "not_needed", "retry": "safe", "guidance": "No recovery is required."}}})

    def validate_public_result(self, value: Any) -> bool:
        try:
            payload = value["payload"]
            target = payload["target"]
            data = payload["data"]
            return (
                isinstance(value, Mapping)
                and set(value) == {"actionId", "payload"}
                and value["actionId"] == self.action_id
                and _valid_completed_project_payload(
                    payload,
                    target_keys={"id", "name"},
                    data_keys={"previousName", "currentName"},
                    evidence_kind="context_readback",
                )
                and _PROJECT_ID.fullmatch(target["id"]) is not None
                and len(target["id"]) <= 160
                and all(
                    isinstance(name, str) and 1 <= len(name) <= 1024
                    for name in (target["name"], data["previousName"], data["currentName"])
                )
                and data["currentName"] == target["name"]
                and payload["changed"] == (data["previousName"] != data["currentName"])
            )
        except Exception:
            return False


@dataclass(frozen=True)
class ProjectSettingDescriptor:
    operation_class = "mutation"
    version = 1
    action_id = "cutagent.action.project.settings_set"
    capability_id = _CAPABILITY_IDS[action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != {"key", "value"}:
            raise ValidationError("Project setting input must contain key and value.")
        if any(not isinstance(value[key], str) or not value[key] for key in ("key", "value")):
            raise ValidationError("Project setting key and value must be non-empty strings.")
        if len(value["key"]) > 1024 or len(value["value"]) > 4096:
            raise ValidationError("Project setting input exceeded its public contract limit.")
        return dict(value)

    def _snapshot(self, context: Mapping[str, Any], key: str) -> dict[str, Any]:
        conn = get_connection(require_project=True)
        return {"value": conn.project.GetSetting(key), "protected": _project_protected_state(conn, context)}

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        before = self._snapshot(context, value["key"])
        return {"targets": [_target(context)], "preState": before, "impact": _impact(context, self.action_id, value),
                "lowering": dict(value), "verification": {"minimumEvidence": ["readback", "structural"]},
                "recovery": {"strategy": "restore_previous_setting_or_require_manual_recovery"}}

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        return {"targets": [_target(context)], "preState": self._snapshot(context, prepared["lowering"]["key"])}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        conn = get_connection(require_project=True)
        _assert_native_project_binding(context, conn)
        data = prepared["lowering"]
        if conn.project.SetSetting(data["key"], data["value"]) is False:
            raise APICallFailed("DaVinci Resolve rejected the project setting write.")
        return {"requested": data["value"], "applied": conn.project.GetSetting(data["key"])}

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        key = prepared["lowering"]["key"]
        current = self._snapshot(context, key)
        passed = (
            _project_setting_values_match(key, result["applied"], result["requested"])
            and _project_setting_values_match(key, current["value"], result["requested"])
            and current["protected"] == prepared["preState"]["protected"]
        )
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, current),
                "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        key = prepared["lowering"]["key"]
        previous = prepared["preState"]["value"]
        previous_runtime = _project_setting_runtime_value(key, previous)
        restored = False
        if previous_runtime is not None:
            try:
                conn = get_connection(require_project=True)
                _assert_native_project_binding(context, conn)
                restored = conn.project.SetSetting(key, previous_runtime) is not False
                restored = restored and _project_setting_values_match(
                    key, conn.project.GetSetting(key), previous
                )
            except Exception:
                restored = False
        return {"outcome": "succeeded" if restored else "manual_required", "attempted": True,
                "manualActionRequired": not restored}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        key = prepared["lowering"]["key"]
        requested = result["requested"]
        previous = prepared["preState"]["value"]
        applied = result["applied"]
        requested_public, applied_public, previous_public = _project_setting_public_values(
            key, requested, applied, previous
        )
        return _assert_public({"actionId": self.action_id, "payload": {"status": "completed", "changed": not _project_setting_values_match(key, previous, applied),
            "target": {"key": key}, "data": {"requestedValue": requested_public, "appliedValue": applied_public, "previousValue": previous_public},
            "verification": {"outcome": "passed", "evidence": [{"kind": "structural_readback", "summary": "Project setting readback matched."}], "protectedState": "preserved"},
            "recovery": {"state": "not_needed", "retry": "safe", "guidance": "No recovery is required."}}})

    def validate_public_result(self, value: Any) -> bool:
        try:
            payload = value["payload"]
            target = payload["target"]
            data = payload["data"]
            return (
                isinstance(value, Mapping)
                and set(value) == {"actionId", "payload"}
                and value["actionId"] == self.action_id
                and _valid_completed_project_payload(
                    payload,
                    target_keys={"key"},
                    data_keys={"requestedValue", "appliedValue", "previousValue"},
                    evidence_kind="structural_readback",
                )
                and isinstance(target["key"], str)
                and 1 <= len(target["key"]) <= 1024
                and all(
                    isinstance(data[key], str) and 1 <= len(data[key]) <= 4096
                    for key in ("requestedValue", "appliedValue")
                )
                and (
                    data["previousValue"] is None
                    or isinstance(data["previousValue"], str)
                    and len(data["previousValue"]) <= 4096
                )
                and _project_setting_values_match(target["key"], data["appliedValue"], data["requestedValue"])
                and payload["changed"] == (
                    not _project_setting_values_match(target["key"], data["previousValue"], data["appliedValue"])
                )
            )
        except Exception:
            return False


_RENDER_SETTING_KEYS = MappingProxyType({
    "outputName": "CustomName", "width": "FormatWidth", "height": "FormatHeight", "fps": "FrameRate",
    "exportVideo": "ExportVideo", "exportAudio": "ExportAudio", "audioCodec": "AudioCodec",
    "audioBitDepth": "AudioBitDepth", "audioSampleRate": "AudioSampleRate",
})


@dataclass(frozen=True)
class RenderMutationDescriptor:
    action_id: str
    normalize: Callable[[Any], Mapping[str, Any]]
    apply: Callable[[Any, Mapping[str, Any]], Any]
    project: Callable[[Mapping[str, Any], Mapping[str, Any], Any], Any]
    operation_class = "mutation"
    version = 1

    @property
    def capability_id(self) -> str:
        return _CAPABILITY_IDS[self.action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        return _canonical(self.normalize(value))

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        before, custody = _capture_render_snapshot(get_connection(require_project=True), context)
        return {"targets": [_target(context)], "preState": before, "impact": _impact(context, self.action_id, value),
                "lowering": {"input": dict(value)}, "verification": {"minimumEvidence": ["readback", "structural"]},
                "recovery": {"strategy": "restore_exact_render_snapshot_or_require_manual_recovery", "custody": custody}}

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        conn = get_connection(require_project=True)
        current, custody = _capture_render_snapshot(conn, context)
        _release_render_snapshot(conn, custody)
        return {"targets": [_target(context)], "preState": current}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        conn = get_connection(require_project=True)
        _assert_native_project_binding(context, conn)
        applied = self.apply(conn, prepared["lowering"]["input"])
        after, custody = _capture_render_snapshot(conn, context)
        return {**dict(applied), "after": after, "afterCustody": custody}

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        conn = get_connection(require_project=True)
        after, settled_custody = _capture_render_snapshot(conn, context)
        expected = result.get("matches") if isinstance(result, Mapping) else None
        matched = isinstance(after, Mapping) and callable(expected) and expected(after)
        protected = isinstance(after, Mapping) and after.get("protected") == prepared["preState"]["protected"]
        passed = bool(matched and protected)
        after_custody = result.get("afterCustody") if isinstance(result, Mapping) else None
        _release_render_snapshot(conn, settled_custody)
        if isinstance(after_custody, Mapping):
            _release_render_snapshot(conn, after_custody)
        if isinstance(result, dict):
            result["after"] = after
        if passed:
            _release_render_snapshot(conn, prepared["recovery"]["custody"])
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, after),
                "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        restored = _restore_render_snapshot(
            get_connection(require_project=True), context, prepared["preState"], prepared["recovery"]["custody"]
        )
        return {"outcome": "succeeded" if restored else "manual_required", "attempted": True,
                "manualActionRequired": not restored}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context
        return _assert_public(self.project(prepared["preState"], prepared["lowering"]["input"], result))

    def validate_public_result(self, value: Any) -> bool:
        return _validate_render_result(self.action_id, value)


@dataclass(frozen=True)
class RenderPresetMutationDescriptor:
    action_id: str
    operation_class = "mutation"
    version = 1

    @property
    def capability_id(self) -> str:
        return _CAPABILITY_IDS[self.action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != {"presetName"}:
            raise ValidationError("Render preset input must contain only presetName.")
        name = value["presetName"]
        if not isinstance(name, str) or not name.strip() or len(name) > 1024:
            raise ValidationError("Render presetName must be non-empty.")
        return {"presetName": name.strip()}

    @staticmethod
    def _snapshot(context: Mapping[str, Any]) -> dict[str, Any]:
        conn = get_connection(require_project=True)
        getter = getattr(conn.project, "GetRenderPresetList", None)
        presets = getter() if callable(getter) else None
        if not isinstance(presets, list):
            raise APICallFailed("DaVinci Resolve render-preset readback is unavailable.")
        if any(not isinstance(item, str) or not item.strip() for item in presets) or len(set(presets)) != len(presets):
            raise APICallFailed("DaVinci Resolve returned an ambiguous render-preset catalog.")
        return {
            "presets": sorted(presets),
            "protected": _project_protected_state(conn, context),
        }

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        before = self._snapshot(context)
        name = value["presetName"]
        if self.action_id.endswith("preset_save") and name in before["presets"]:
            raise ValidationError("Render preset already exists; overwrite is forbidden.")
        target = _target(context)
        return {
            "targets": [target], "preState": before,
            "impact": _impact(context, self.action_id, value),
            "lowering": {"presetName": value["presetName"]},
            "verification": {"minimumEvidence": ["readback", "structural"]},
            "recovery": {"strategy": "verify_unchanged_or_require_manual_recovery"},
        }

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        return {"targets": [_target(context)], "preState": self._snapshot(context)}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        conn = get_connection(require_project=True)
        _assert_native_project_binding(context, conn)
        name = prepared["lowering"]["presetName"]
        if self.action_id.endswith("preset_save"):
            if name in prepared["preState"]["presets"]:
                raise ValidationError("Render preset already exists; overwrite is forbidden.")
            saver = getattr(conn.project, "SaveAsNewRenderPreset", None)
            if not callable(saver) or saver(name) is not True:
                raise APICallFailed("DaVinci Resolve rejected the render-preset save.")
            return {"presetName": name, "saved": True}
        if name not in prepared["preState"]["presets"]:
            raise ValidationError("Render preset does not exist.")
        result = render_engine.delete_render_preset(conn, name)
        return {"presetName": name, "deleted": bool(result.get("deleted", True))}

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        after = self._snapshot(context)
        name = prepared["lowering"]["presetName"]
        expected_present = self.action_id.endswith("preset_save")
        expected = set(prepared["preState"]["presets"])
        expected = expected | {name} if expected_present else expected - {name}
        passed = set(after["presets"]) == expected and after["protected"] == prepared["preState"]["protected"]
        result["after"] = after
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, after), "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        # A catalog name is not an operation-owned identity. A failed save or
        # concurrent creation cannot authorize deletion of the matching preset.
        # Report partial failures explicitly; do not manufacture a destructive rollback.
        try:
            restored = self._snapshot(context) == prepared["preState"]
        except Exception:
            restored = False
        return {"outcome": "succeeded" if restored else "manual_required", "attempted": False, "manualActionRequired": not restored}


    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context
        key = "saved" if self.action_id.endswith("preset_save") else "deleted"
        return _assert_public({"actionId": self.action_id, "data": {"presetName": prepared["lowering"]["presetName"], key: bool(result[key])}})

    def validate_public_result(self, value: Any) -> bool:
        try:
            key = "saved" if self.action_id.endswith("preset_save") else "deleted"
            return set(value) == {"actionId", "data"} and value["actionId"] == self.action_id and value["data"][key] is True
        except Exception:
            return False


@dataclass(frozen=True)
class RenderQueueDeleteDescriptor:
    action_id = "cutagent.action.render.delete"
    operation_class = "mutation"
    version = 1
    capability_id = _CAPABILITY_IDS[action_id]

    def validate_input(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != {"selection"} or not isinstance(value["selection"], Mapping):
            raise ValidationError("Render delete input must contain one selection.")
        selection = dict(value["selection"])
        if selection == {"kind": "all"}:
            return {"selection": selection}
        if set(selection) == {"kind", "jobId"} and selection.get("kind") == "job" and isinstance(selection.get("jobId"), str) and selection["jobId"]:
            return {"selection": selection}
        raise ValidationError("Render delete selection must identify one job or the complete queue.")

    @staticmethod
    def _job_bindings(context: Mapping[str, Any]) -> dict[str, dict[str, str]]:
        project, _ = _project_binding(context)
        rows = project.get("nativeRenderJobs")
        if not isinstance(rows, (list, tuple)):
            raise ValidationError("Prepared render deletion omitted private render-job bindings.")
        bindings: dict[str, dict[str, str]] = {}
        native_ids: set[str] = set()
        for raw in rows:
            if not isinstance(raw, Mapping) or set(raw) != {"jobId", "nativeJobId", "revision"}:
                raise ValidationError("Prepared render deletion has a malformed render-job binding.")
            if any(not isinstance(raw.get(key), str) or not raw[key] for key in raw):
                raise ValidationError("Prepared render deletion has a malformed render-job binding.")
            row = dict(raw)
            if (
                not row["jobId"].startswith("render_job_")
                or not row["revision"].startswith("revision_")
                or row["jobId"] == row["nativeJobId"]
                or row["jobId"] in bindings
                or row["nativeJobId"] in native_ids
            ):
                raise ValidationError("Prepared render deletion has an ambiguous render-job binding.")
            bindings[row["jobId"]] = row
            native_ids.add(row["nativeJobId"])
        return bindings

    @staticmethod
    def _assert_exact_targets(
        context: Mapping[str, Any], targets: list[dict[str, str]]
    ) -> None:
        exact = context.get("exactRequestBinding")
        identities = exact.get("identities") if isinstance(exact, Mapping) else None
        revisions = exact.get("revisions") if isinstance(exact, Mapping) else None
        exact_ids = identities.get("targetIds") if isinstance(identities, Mapping) else None
        exact_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
        expected_ids = [target["stableId"] for target in targets]
        expected_revisions = {
            target["stableId"]: target["revision"] for target in targets
        }
        if exact_ids != expected_ids or exact_revisions != expected_revisions:
            raise ValidationError(
                "Prepared render deletion targets drifted from the exact carrier binding."
            )

    @classmethod
    def _snapshot(cls, context: Mapping[str, Any]) -> dict[str, Any]:
        conn = get_connection(require_project=True)
        jobs = conn.project.GetRenderJobList()
        if not isinstance(jobs, list):
            raise APICallFailed("DaVinci Resolve render-queue readback is unavailable.")
        rows = [_canonical(dict(job)) for job in jobs if isinstance(job, Mapping)]
        if len(rows) != len(jobs):
            raise APICallFailed("DaVinci Resolve returned a malformed render queue.")
        native_job_ids = [job.get("JobId") for job in rows]
        if any(not isinstance(job_id, str) or not job_id for job_id in native_job_ids):
            raise ValidationError("DaVinci Resolve returned a malformed native render-job identity.")
        if len(set(native_job_ids)) != len(native_job_ids):
            raise ValidationError("DaVinci Resolve returned duplicate native render-job identities.")
        bindings = cls._job_bindings(context)
        public_by_native = {row["nativeJobId"]: row["jobId"] for row in bindings.values()}
        return {
            "jobs": rows,
            "publicJobIds": sorted(
                public_by_native[job["JobId"]]
                for job in rows
                if job["JobId"] in public_by_native
            ),
            "unboundNativeJobIds": sorted(
                job["JobId"] for job in rows
                if job["JobId"] not in public_by_native
            ),
            "protected": _project_protected_state(conn, context),
        }

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        before = self._snapshot(context)
        selection = value["selection"]
        bindings = self._job_bindings(context)
        if selection["kind"] == "all":
            if before["unboundNativeJobIds"] or not before["jobs"]:
                raise ValidationError("The complete render queue lacks exact stable CutAgent job bindings.")
            selected_bindings = [bindings[job_id] for job_id in before["publicJobIds"]]
        else:
            binding = bindings.get(selection["jobId"])
            if binding is None or binding["nativeJobId"] not in {
                job["JobId"] for job in before["jobs"]
            }:
                raise ValidationError("The selected stable render job does not exist.")
            selected_bindings = [binding]
        if not selected_bindings:
            raise ValidationError("The selected render job does not exist.")
        targets = [
            {"kind": "render_job", "stableId": row["jobId"], "revision": row["revision"]}
            for row in selected_bindings
        ]
        self._assert_exact_targets(context, targets)
        impact = _impact(context, self.action_id, value)
        impact["effects"][0]["kind"] = "delete"
        impact["effects"][0]["targets"] = targets
        return {"targets": targets, "preState": before, "impact": impact, "lowering": {
            "selection": selection,
            "nativeJobIds": [row["nativeJobId"] for row in selected_bindings],
        }, "verification": {"minimumEvidence": ["readback", "structural"]}, "recovery": {"strategy": "manual_queue_reconstruction_if_verification_fails"}}

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        return {"targets": prepared["targets"], "preState": self._snapshot(context)}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        conn = get_connection(require_project=True)
        _assert_native_project_binding(context, conn)
        selection = prepared["lowering"]["selection"]
        native_ids = prepared["lowering"]["nativeJobIds"]
        return render_engine.delete_render_job(
            conn,
            job_id=native_ids[0] if selection["kind"] == "job" else None,
            all_jobs=selection["kind"] == "all",
        )

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        after = self._snapshot(context)
        selection = prepared["lowering"]["selection"]
        native_ids = set(prepared["lowering"]["nativeJobIds"])
        if selection["kind"] == "all":
            deleted = not after["jobs"]
        else:
            deleted = all(str(job.get("JobId")) not in native_ids for job in after["jobs"])
        protected = after["protected"] == {
            **prepared["preState"]["protected"], "renderJobIds": sorted(str(job.get("JobId")) for job in after["jobs"])
        }
        passed = bool(result.get("deleted") and deleted and protected)
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, after), "protectedStatePreserved": passed}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del context, prepared, failure
        return {"outcome": "manual_required", "attempted": False, "manualActionRequired": True}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        del context
        selection = prepared["lowering"]["selection"]
        deleted_ids = (
            prepared["preState"]["publicJobIds"]
            if selection["kind"] == "all"
            else [selection["jobId"]]
        )
        return _assert_public({
            "actionId": self.action_id,
            "data": {"deletedJobIds": deleted_ids if result.get("deleted") else []},
        })

    def validate_public_result(self, value: Any) -> bool:
        try:
            rows = value["data"]["deletedJobIds"]
            return (
                isinstance(value, Mapping)
                and set(value) == {"actionId", "data"}
                and value["actionId"] == self.action_id
                and isinstance(value["data"], Mapping)
                and set(value["data"]) == {"deletedJobIds"}
                and isinstance(rows, list)
                and len(set(rows)) == len(rows)
                and all(isinstance(item, str) and item for item in rows)
            )
        except Exception:
            return False


def _object(value: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not set(value) <= allowed:
        raise ValidationError("Render action input has an invalid shape.")
    return dict(value)


def _apply_mode(conn: Any, value: Mapping[str, Any]) -> dict[str, Any]:
    requested = 0 if value["mode"] == "individual" else 1
    before = conn.project.GetCurrentRenderMode()
    if conn.project.SetCurrentRenderMode(requested) is False:
        raise APICallFailed("DaVinci Resolve rejected the render mode.")
    return {"before": before, "matches": lambda current: current["mode"] == requested}


def _apply_settings(conn: Any, value: Mapping[str, Any]) -> dict[str, Any]:
    settings = {runtime: value[public] for public, runtime in _RENDER_SETTING_KEYS.items() if public in value}
    if "codec" in value and "format" not in value:
        raise ValidationError("Render codec requires format in the same typed action.")
    if "format" in value:
        format_name = value["format"]
        codec_name = value.get("codec")
        if codec_name is None:
            current = conn.project.GetCurrentRenderFormatAndCodec()
            codec_name = current.get("codec") or current.get("Codec")
        if not codec_name or conn.project.SetCurrentRenderFormatAndCodec(format_name, codec_name) is False:
            raise APICallFailed("DaVinci Resolve rejected the render format and codec.")
    if settings and conn.project.SetRenderSettings(settings) is False:
        raise APICallFailed("DaVinci Resolve rejected the typed render settings.")

    def matches(after: Mapping[str, Any]) -> bool:
        if any(after["settings"].get(key) != expected for key, expected in settings.items()):
            return False
        current = after["formatCodec"]
        return "format" not in value or value["format"] in {current.get("format"), current.get("Format")}

    return {"applied": settings, "matches": matches}


def _apply_dict_settings(conn: Any, settings: Mapping[str, Any]) -> dict[str, Any]:
    if conn.project.SetRenderSettings(dict(settings)) is False:
        raise APICallFailed("DaVinci Resolve rejected the render settings.")
    return {"matches": lambda after: all(after["settings"].get(key) == item for key, item in settings.items())}


def _apply_subtitle_settings(conn: Any, value: Mapping[str, Any]) -> dict[str, Any]:
    setter = conn.project.SetRenderSettings
    # DaVinci Resolve retains the previous subtitle codec while export remains
    # enabled. Disable first so a format transition has an observable effect.
    for settings in (
        {"ExportSubtitle": False},
        {"SubtitleFormat": value["format"]},
        {"ExportSubtitle": value["enabled"]},
    ):
        if setter(settings) is False:
            raise APICallFailed("DaVinci Resolve rejected the render settings.")
    return {"matches": lambda after: (
        after["settings"].get("ExportSubtitle") == value["enabled"]
        and after["settings"].get("SubtitleFormat") == value["format"]
    )}


def _apply_preset(conn: Any, value: Mapping[str, Any]) -> dict[str, Any]:
    before, before_custody = _capture_render_snapshot(conn)
    _release_render_snapshot(conn, before_custody)
    loaded = render_engine.load_render_preset(conn, value["presetName"])
    after, after_custody = _capture_render_snapshot(conn)
    _release_render_snapshot(conn, after_custody)
    return {
        "loaded": loaded,
        "matches": lambda current: (
            isinstance(loaded, Mapping)
            and loaded.get("loaded") is True
            and loaded.get("preset") == value["presetName"]
            and current == after
            and current != before
        ),
    }


def _apply_archive_settings(conn: Any, value: Mapping[str, Any]) -> dict[str, Any]:
    kwargs = {
        "target": value.get("targetDirectory"),
        "name": value.get("outputName"),
        "format": value.get("containerFormat", "QuickTime"),
        "codec": value.get("videoCodec", "Apple ProRes"),
        "audio_codec": value.get("audioCodec", "Linear PCM"),
        "audio_bit_depth": value.get("audioBitDepth", 32),
        "audio_sample_rate": value.get("audioSampleRate", 48_000),
        "width": value.get("width"),
        "height": value.get("height"),
        "fps": value.get("fps"),
        "separate_audio_tracks": False,
    }
    result = render_engine.set_archive_render_settings(conn, **kwargs)
    expected = {
        key: item
        for key, item in result["settings"].items()
        if item is not None
    }
    return {
        **result,
        "matches": lambda current: all(
            current["settings"].get(key) == item for key, item in expected.items()
        ),
    }


def _valid_revision(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"revisionBefore", "revisionAfter", "changed"}
        and _REVISION.fullmatch(str(value.get("revisionBefore", ""))) is not None
        and _REVISION.fullmatch(str(value.get("revisionAfter", ""))) is not None
        and isinstance(value.get("changed"), bool)
    )


def _validate_render_result(action_id: str, value: Any) -> bool:
    try:
        if not isinstance(value, Mapping) or set(value) != {"actionId", "data"} or value["actionId"] != action_id:
            return False
        data = value["data"]
        if not isinstance(data, Mapping):
            return False
        if action_id == "cutagent.action.render.mode.set":
            return set(data) == {"mode", "changed"} and data["mode"] in {"individual", "single"} and isinstance(data["changed"], bool)
        if action_id == "cutagent.action.render.alpha":
            return set(data) == {"enabled", "mode"} and isinstance(data["enabled"], bool) and data["mode"] in {"premultiplied", "straight"}
        if action_id == "cutagent.action.render.encoding":
            return (set(data) == {"profile", "multiPass", "networkOptimization", "revision"}
                    and isinstance(data["profile"], str) and bool(data["profile"])
                    and isinstance(data["multiPass"], bool) and isinstance(data["networkOptimization"], bool)
                    and _valid_revision(data["revision"]))
        if action_id == "cutagent.action.render.subtitles":
            return (set(data) == {"enabled", "format", "revision"} and isinstance(data["enabled"], bool)
                    and data["format"] in {"BurnIn", "EmbeddedCaptions", "SeparateFile"}
                    and _valid_revision(data["revision"]))
        if action_id == "cutagent.action.render.preset_load":
            return (set(data) == {"presetName", "loaded", "revision"} and isinstance(data["presetName"], str)
                    and bool(data["presetName"]) and data["loaded"] is True and _valid_revision(data["revision"]))
        if action_id in {
            "cutagent.action.render.settings_set",
            "cutagent.action.render.archive_settings",
        }:
            rows = data.get("appliedSettings")
            return (set(data) == {"appliedSettings", "revision"} and isinstance(rows, list)
                    and all(isinstance(row, Mapping) and set(row) == {"key", "value"}
                            and isinstance(row["key"], str) and bool(row["key"])
                            and (row["value"] is None or isinstance(row["value"], (str, int, float, bool))) for row in rows)
                    and _valid_revision(data["revision"]))
        return False
    except Exception:
        return False


def _render_descriptors() -> dict[str, RenderMutationDescriptor]:
    def result(action_id: str, data: Callable[[Mapping[str, Any], Mapping[str, Any], Any], Mapping[str, Any]]):
        return lambda before, value, private: {"actionId": action_id, "data": dict(data(before, value, private))}

    def normalize_mode(value: Any) -> Mapping[str, Any]:
        data = _object(value, {"mode"})
        if set(data) != {"mode"} or data["mode"] not in {"individual", "single"}:
            raise ValidationError("Render mode must be individual or single.")
        return data

    def normalize_encoding(value: Any) -> Mapping[str, Any]:
        data = _object(value, {"profile", "multiPass", "networkOptimization"})
        if not isinstance(data.get("profile"), str) or not data["profile"]:
            raise ValidationError("Encoding profile is required.")
        data.setdefault("multiPass", False)
        data.setdefault("networkOptimization", False)
        if not all(isinstance(data[key], bool) for key in ("multiPass", "networkOptimization")):
            raise ValidationError("Encoding flags must be booleans.")
        return data

    def normalize_subtitles(value: Any) -> Mapping[str, Any]:
        data = _object(value, {"enabled", "format"})
        if data.get("format") not in {"BurnIn", "EmbeddedCaptions", "SeparateFile"}:
            raise ValidationError("Subtitle format is invalid.")
        data.setdefault("enabled", True)
        if not isinstance(data["enabled"], bool):
            raise ValidationError("Subtitle enabled must be boolean.")
        return data

    def normalize_alpha(value: Any) -> Mapping[str, Any]:
        data = _object(value, {"enabled", "mode"})
        data.setdefault("enabled", True)
        data.setdefault("mode", "premultiplied")
        if not isinstance(data["enabled"], bool) or data["mode"] not in {"premultiplied", "straight"}:
            raise ValidationError("Alpha render input is invalid.")
        return data

    def normalize_settings(value: Any) -> Mapping[str, Any]:
        data = _object(value, set(_RENDER_SETTING_KEYS) | {"format", "codec", "targetDirectory"})
        if "targetDirectory" in data:
            raise ValidationError("Render targetDirectory requires a managed-artifact reservation.")
        for key in ("width", "height", "audioBitDepth", "audioSampleRate"):
            if key in data and (not isinstance(data[key], int) or isinstance(data[key], bool) or data[key] < 1):
                raise ValidationError(f"{key} must be a positive integer.")
        if "fps" in data and (not isinstance(data["fps"], (int, float)) or isinstance(data["fps"], bool) or data["fps"] <= 0):
            raise ValidationError("fps must be positive.")
        return data

    def normalize_archive(value: Any) -> Mapping[str, Any]:
        data = _object(value, {
            "targetDirectory", "outputName", "containerFormat", "videoCodec",
            "audioCodec", "audioBitDepth", "audioSampleRate", "width", "height",
            "fps", "separateAudioTracks",
        })
        if data.get("separateAudioTracks") is True:
            raise ValidationError(
                "DaVinci Resolve's public API cannot configure or verify separate embedded audio tracks."
            )
        data["separateAudioTracks"] = False
        if "targetDirectory" in data:
            from pathlib import Path

            target = Path(data["targetDirectory"]).expanduser()
            if not target.is_absolute() or not target.is_dir():
                raise ValidationError("Archive render targetDirectory must be an existing absolute directory.")
            data["targetDirectory"] = str(target.resolve())
        for key in ("outputName", "containerFormat", "videoCodec", "audioCodec"):
            if key in data and (not isinstance(data[key], str) or not data[key].strip()):
                raise ValidationError(f"{key} must be non-empty text.")
            if key in data:
                data[key] = data[key].strip()
        for key in ("audioBitDepth", "audioSampleRate", "width", "height"):
            if key in data and (
                not isinstance(data[key], int) or isinstance(data[key], bool) or data[key] < 1
            ):
                raise ValidationError(f"{key} must be a positive integer.")
        if "fps" in data and (
            not isinstance(data["fps"], (int, float))
            or isinstance(data["fps"], bool)
            or data["fps"] <= 0
        ):
            raise ValidationError("fps must be positive.")
        return data

    def rev(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
        before_rev = _revision(before)
        after_rev = _revision(after)
        return {"revisionBefore": before_rev, "revisionAfter": after_rev, "changed": before_rev != after_rev}

    specs: dict[str, RenderMutationDescriptor] = {}
    aid = "cutagent.action.render.mode.set"
    specs[aid] = RenderMutationDescriptor(aid, normalize_mode, _apply_mode,
        result(aid, lambda before, value, private: {"mode": value["mode"], "changed": before["mode"] != (0 if value["mode"] == "individual" else 1)}))
    aid = "cutagent.action.render.encoding"
    specs[aid] = RenderMutationDescriptor(aid, normalize_encoding,
        lambda conn, value: _apply_dict_settings(conn, {"EncodingProfile": value["profile"], "MultiPassEncode": value["multiPass"], "NetworkOptimization": value["networkOptimization"]}),
        result(aid, lambda before, value, private: {**value, "revision": rev(before, private["after"])}))
    aid = "cutagent.action.render.subtitles"
    specs[aid] = RenderMutationDescriptor(aid, normalize_subtitles, _apply_subtitle_settings,
        result(aid, lambda before, value, private: {**value, "revision": rev(before, private["after"])}))
    aid = "cutagent.action.render.alpha"
    specs[aid] = RenderMutationDescriptor(aid, normalize_alpha,
        lambda conn, value: {**render_engine.set_render_alpha_settings(conn, enable=value["enabled"], mode=value["mode"]),
                             "matches": lambda after: after["settings"].get("ExportAlpha") == value["enabled"] and after["settings"].get("AlphaMode") == value["mode"]},
        result(aid, lambda before, value, private: value))
    return specs


_BASE_PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS = (
    "cutagent.action.project.rename",
    "cutagent.action.project.settings_set",
    "cutagent.action.render.alpha",
    "cutagent.action.render.encoding",
    "cutagent.action.render.mode.set",
    "cutagent.action.render.subtitles",
    "cutagent.action.render.preset_save",
    "cutagent.action.render.preset_update",
)

from .project_media_extended_prepared_action import (  # noqa: E402
    EXTENDED_PROJECT_MEDIA_CALLABLE_ACTION_IDS,
    extended_project_media_prepared_action_descriptors,
)
from .media_residual_prepared_action import (  # noqa: E402
    MEDIA_RESIDUAL_CALLABLE_ACTION_IDS,
    residual_media_prepared_action_descriptors,
)

PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS = (
    *_BASE_PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS,
    *EXTENDED_PROJECT_MEDIA_CALLABLE_ACTION_IDS,
    *MEDIA_RESIDUAL_CALLABLE_ACTION_IDS,
)


def project_render_storage_media_prepared_action_descriptors() -> Mapping[str, Any]:
    """Return this domain's exact contribution to the sole shared registry."""
    from .render_preset_update_prepared_action import RenderPresetUpdateDescriptor
    descriptors: dict[str, Any] = {
        RenderPresetUpdateDescriptor.action_id: RenderPresetUpdateDescriptor(),
        ProjectRenameDescriptor.action_id: ProjectRenameDescriptor(),
        ProjectSettingDescriptor.action_id: ProjectSettingDescriptor(),
        **_render_descriptors(),
        "cutagent.action.render.preset_save": RenderPresetMutationDescriptor("cutagent.action.render.preset_save"),
        **extended_project_media_prepared_action_descriptors(),
        **residual_media_prepared_action_descriptors(),
    }
    if set(descriptors) != set(PROJECT_RENDER_STORAGE_MEDIA_CALLABLE_ACTION_IDS):
        raise RuntimeError("Project/render descriptor contribution is incomplete.")
    return MappingProxyType(descriptors)
