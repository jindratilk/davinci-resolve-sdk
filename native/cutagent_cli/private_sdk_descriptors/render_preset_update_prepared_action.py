"""Prepared update bound to both the target preset and current render settings."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any, Mapping

from ..connection import get_connection
from ..core import render_engine
from ..core._render_engine.preset_update import update_render_preset
from ..errors import ValidationError
from .project_render_storage_media_prepared_action import (
    _assert_native_project_binding, _assert_public, _evidence, _impact,
    _project_protected_state,
)


def _same_state(left: Any, right: Any) -> bool:
    # The production authority freezes request/prepared lists to tuples and
    # mappings to read-only proxies. Compare JSON meaning, not mutability.
    from ..sdk_prepared_action import _deep_thaw, canonical_bytes
    return canonical_bytes(_deep_thaw(left)) == canonical_bytes(_deep_thaw(right))


class RenderPresetUpdateDescriptor:
    action_id = "cutagent.action.render.preset_update"
    operation_class = "mutation"
    version = 1
    capability_id = "render.preset_save"
    @staticmethod
    def validate_input(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != {"presetName"}:
            raise ValidationError("Render preset update input must contain only presetName.")
        name = value["presetName"]
        if (
            not isinstance(name, str)
            or not name
            or len(name) > 1024
            or name != name.strip()
        ):
            raise ValidationError("Render preset update requires an exact non-empty presetName.")
        return {"presetName": name}

    @staticmethod
    def _target(context: Mapping[str, Any], name: str) -> dict[str, str]:
        exact = context.get("exactRequestBinding")
        identities = exact.get("identities") if isinstance(exact, Mapping) else None
        revisions = exact.get("revisions") if isinstance(exact, Mapping) else None
        project_revision = revisions.get("project") if isinstance(revisions, Mapping) else None
        target_ids = identities.get("targetIds") if isinstance(identities, Mapping) else None
        target_revisions = revisions.get("targets") if isinstance(revisions, Mapping) else None
        if not isinstance(project_revision, str) or not project_revision:
            raise ValidationError("Render preset update omitted its exact project revision binding.")
        stable_id = f"render_preset_{hashlib.sha256(name.encode()).hexdigest()[:32]}"
        revision = "revision_" + hashlib.sha256(
            f"render_preset\0{name}\0{project_revision}".encode()
        ).hexdigest()
        if (not isinstance(target_ids, (list, tuple)) or tuple(target_ids) != (stable_id,)
                or target_revisions != {stable_id: revision}):
            raise ValidationError("Render preset update target drifted from the exact carrier binding.")
        return {"kind": "runtime_setting", "stableId": stable_id, "revision": revision}

    @staticmethod
    def _snapshot(context: Mapping[str, Any], name: str) -> dict[str, Any]:
        conn = get_connection(require_project=True)
        _assert_native_project_binding(context, conn)
        catalog = render_engine._render_preset_catalog_names(conn)
        if name not in catalog:
            raise ValidationError("Render preset does not exist; update requires an exact name.")
        with tempfile.TemporaryDirectory(prefix="cutagent-preset-preparation-") as directory:
            _, original, _ = render_engine._export_render_context_preset(conn, name, Path(directory))
        current = render_engine._snapshot_render_context_with_preset(conn)
        try:
            state = {
                "presetSha256": hashlib.sha256(original).hexdigest(),
                "settingsSha256": hashlib.sha256(current["canonical_xml"].encode()).hexdigest(),
                "presets": sorted(catalog),
                "protected": _project_protected_state(conn, context),
            }
        finally:
            render_engine._discard_render_context_preset_snapshot(conn, current)
        _assert_native_project_binding(context, conn)
        return state

    def prepare(self, context: Mapping[str, Any], value: Mapping[str, Any]) -> dict[str, Any]:
        target = self._target(context, value["presetName"])
        impact = _impact(context, self.action_id, value)
        impact["effects"][0]["targets"] = [target]
        return {
            "targets": [target], "preState": self._snapshot(context, value["presetName"]),
            "impact": impact,
            "lowering": {"presetName": value["presetName"]},
            "verification": {"minimumEvidence": ["readback", "structural"]},
            "recovery": {"strategy": "verify_unchanged_or_require_manual_recovery"},
        }

    def resolve_current(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
        name = prepared["lowering"]["presetName"]
        return {"targets": [self._target(context, name)], "preState": self._snapshot(context, name)}

    def execute(self, context: Mapping[str, Any], prepared: Mapping[str, Any]) -> Any:
        conn = get_connection(require_project=True)
        _assert_native_project_binding(context, conn)
        return update_render_preset(
            conn, prepared["lowering"]["presetName"],
            expected_preset_sha256=prepared["preState"]["presetSha256"],
            expected_settings_sha256=prepared["preState"]["settingsSha256"],
        )

    def verify(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> dict[str, Any]:
        after = self._snapshot(context, prepared["lowering"]["presetName"])
        before = prepared["preState"]
        passed = (
            result.get("updated") is True and result.get("verified") is True
            and after["presetSha256"] == before["settingsSha256"]
            and after["settingsSha256"] == before["settingsSha256"]
            and _same_state(after["presets"], before["presets"])
            and _same_state(after["protected"], before["protected"])
        )
        return {"outcome": "passed" if passed else "failed", "evidence": _evidence(self.action_id, after),
                "protectedStatePreserved": _same_state(after["protected"], before["protected"])}

    def recover(self, context: Mapping[str, Any], prepared: Mapping[str, Any], failure: BaseException) -> dict[str, Any]:
        del failure
        try:
            unchanged = _same_state(self._snapshot(context, prepared["lowering"]["presetName"]), prepared["preState"])
        except Exception:
            unchanged = False
        return {"outcome": "succeeded" if unchanged else "manual_required", "attempted": False,
                "manualActionRequired": not unchanged}

    def project_result(self, context: Mapping[str, Any], prepared: Mapping[str, Any], result: Any) -> Any:
        return _assert_public({"actionId": self.action_id, "data": {
            "presetName": prepared["lowering"]["presetName"], "updated": result["updated"],
        }})

    def validate_public_result(self, value: Any) -> bool:
        return (
            isinstance(value, Mapping) and set(value) == {"actionId", "data"}
            and value["actionId"] == self.action_id and isinstance(value["data"], Mapping)
            and set(value["data"]) == {"presetName", "updated"}
            and isinstance(value["data"]["presetName"], str) and bool(value["data"]["presetName"].strip())
            and len(value["data"]["presetName"]) <= 1024 and value["data"]["updated"] is True
        )
