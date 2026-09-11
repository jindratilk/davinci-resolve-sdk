"""Update an exact existing preset with native export verification."""
from __future__ import annotations

import shutil
import logging
import hashlib
import tempfile
from pathlib import Path

from ...errors import APICallFailed, ValidationError
from .common import _get_callable


def update_render_preset(conn, name: str, *, expected_preset_sha256: str | None = None,
                         expected_settings_sha256: str | None = None) -> dict:
    # Import lazily: the existing context-custody helpers compose this package.
    from .. import render_engine

    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise ValidationError("Render preset update requires an exact non-empty name.")
    updater = _get_callable(getattr(conn, "project", None), "UpdateRenderPreset")
    if updater is None:
        raise APICallFailed("DaVinci Resolve render preset update is unavailable.")
    catalog = render_engine._render_preset_catalog_names(conn)
    if name not in catalog:
        raise ValidationError("Render preset does not exist; update requires an exact name.")

    directory = Path(tempfile.mkdtemp(prefix="cutagent-render-update-"))
    snapshot = None
    backup_path = None
    write_attempted = False
    failure = None
    try:
        backup_path, original, _ = render_engine._export_render_context_preset(conn, name, directory / "before")
        snapshot = render_engine._snapshot_render_context_with_preset(conn)
        if expected_preset_sha256 is not None and hashlib.sha256(original).hexdigest() != expected_preset_sha256:
            raise ValidationError("Render preset changed after preparation.")
        if expected_settings_sha256 is not None and hashlib.sha256(snapshot["canonical_xml"].encode()).hexdigest() != expected_settings_sha256:
            raise ValidationError("Current render settings changed after preparation.")
        expected_catalog = sorted([*catalog, snapshot["preset_name"]])
        if sorted(render_engine._render_preset_catalog_names(conn)) != expected_catalog:
            raise APICallFailed("DaVinci Resolve preset catalog changed before update.")
        write_attempted = True
        if updater(name) is not True:
            raise APICallFailed("DaVinci Resolve did not confirm render preset update.")
        _, canonical, _ = render_engine._export_render_context_preset(conn, name, directory / "after")
        if canonical.decode("utf-8") != snapshot["canonical_xml"]:
            raise APICallFailed("DaVinci Resolve updated preset does not match current render settings.")
        # This helper releases custody and verifies a fresh current-settings
        # snapshot. Loading the already selected preset is a native no-op and
        # is deliberately not used as evidence of the saved settings.
        expected, snapshot = snapshot, None
        render_engine._verify_render_context_after_checkpoint(conn, expected)
        if render_engine._render_preset_catalog_names(conn) != catalog:
            raise APICallFailed("DaVinci Resolve preset update changed the catalog.")
    except Exception as exc:
        failure = exc
    finally:
        if snapshot is not None:
            try:
                render_engine._discard_render_context_preset_snapshot(conn, snapshot)
            except Exception as exc:
                failure = APICallFailed(
                    "DaVinci Resolve render preset update custody cleanup failed.",
                    details={"update_error": str(failure) if failure else None, "cleanup_error": str(exc)},
                    recoverability="manual",
                )
        if failure is None or not write_attempted:
            try:
                shutil.rmtree(directory)
            except OSError:
                # Temporary-file cleanup cannot undo a verified native update or
                # replace a pre-mutation validation error with an unrelated OS error.
                logging.getLogger(__name__).warning(
                    "Temporary render preset verification files could not be fully removed."
                )

    if failure is not None:
        if write_attempted:
            # Preserve the original export for explicit recovery. Never delete
            # or replace a global preset based solely on its name after failure.
            raise APICallFailed(
                "DaVinci Resolve render preset update could not be verified.",
                details={"preset": name, "original_preset_path": str(backup_path), "cause": str(failure)},
                recoverability="manual",
            ) from failure
        raise failure
    return {"preset": name, "updated": True, "verified": True}
