"""Media Storage commands."""

from __future__ import annotations


from pathlib import Path

import typer

from ..connection import get_connection
from ..errors import handle_errors, APICallFailed, ValidationError
from ..output import dry_run_message, is_dry_run, output, set_verification_status, success
from ..policy import enforce_mutation_policy
from ..core import storage_ops

app = typer.Typer(help="Media Storage (disk) operations.")


def _normalize_storage_directory(path: str) -> Path:
    normalized = Path(path).expanduser()
    try:
        resolved = normalized.resolve(strict=False)
    except OSError:
        resolved = normalized.absolute()
    if not resolved.exists():
        raise ValidationError(
            "Storage path does not exist.",
            details={
                "path": path,
                "normalized_path": str(resolved),
                "hint": "Use `storage volumes -j` to inspect DaVinci Resolve storage roots or pass an existing directory.",
            },
            recoverability="not_applicable",
        )
    if not resolved.is_dir():
        raise ValidationError(
            "Storage path must be a directory.",
            details={"path": path, "normalized_path": str(resolved)},
            recoverability="not_applicable",
        )
    return resolved


def _storage_item(path: str | Path, item_type: str, *, source: str, base_path: Path | None = None) -> dict:
    item_path = Path(path)
    if base_path is not None and not item_path.is_absolute():
        item_path = base_path / item_path
    item_path_text = str(item_path)
    return {
        "name": item_path.name or item_path_text,
        "path": item_path_text,
        "type": item_type,
        "source": source,
    }


def _list_local_storage_items(directory: Path) -> list[dict]:
    try:
        children = list(directory.iterdir())
    except OSError as exc:
        raise ValidationError(
            "Storage path cannot be read.",
            details={"path": str(directory), "error": str(exc)},
            recoverability="manual",
        ) from exc

    children.sort(key=lambda child: (not child.is_dir(), child.name.lower()))
    return [
        _storage_item(child, "folder" if child.is_dir() else "file", source="filesystem")
        for child in children
    ]


@app.command("volumes")
@handle_errors
def volumes():
    """List mounted storage volumes."""
    conn = get_connection(require_project=False)

    ms = conn.resolve.GetMediaStorage()
    if not ms:
        raise APICallFailed("Cannot access Media Storage.")

    mount_points = ms.GetMountedVolumeList()
    if not mount_points:
        output([])
        return

    rows = [{"path": p} for p in mount_points]
    output(rows, columns=[("path", "Volume Path")], quiet_key="path")


@app.command("files")
@handle_errors
def files(
    path: str = typer.Argument(..., help="Path to browse"),
):
    """List files in a storage location."""
    directory = _normalize_storage_directory(path)
    conn = get_connection(require_project=False)
    ms = conn.resolve.GetMediaStorage()
    if not ms:
        raise APICallFailed("Cannot access Media Storage.")

    storage_path = str(directory)
    file_list = ms.GetSubFolderList(storage_path)
    if not file_list:
        file_list = []

    # Also get files
    files = ms.GetFileList(storage_path)
    if not files:
        files = []

    all_items = [_storage_item(f, "folder", source="resolve_media_storage", base_path=directory) for f in file_list]
    all_items += [_storage_item(f, "file", source="resolve_media_storage", base_path=directory) for f in files]

    if not all_items:
        all_items = _list_local_storage_items(directory)
        if all_items:
            set_verification_status("verified")

    output(all_items, columns=[("name", "Name"), ("type", "Type")],
           title=f"Storage: {storage_path}", quiet_key="name")


@app.command("import")
@handle_errors
def import_from_storage(
    path: str = typer.Argument(..., help="File/folder path to import"),
):
    """Import media from storage into the Media Pool."""
    enforce_mutation_policy("storage.import", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would import media from storage path: {path}")
        return
    conn = get_connection(require_project=True)
    data = storage_ops.import_from_storage(conn, path)
    success(f"Imported {data['imported_count']} item(s) from storage.")


@app.command("reveal")
@handle_errors
def reveal(
    path: str = typer.Argument(..., help="Path to reveal in Media Storage"),
):
    """Reveal a path in DaVinci Resolve Media Storage."""
    enforce_mutation_policy("storage.reveal", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would reveal a managed storage artifact: {path}")
        return
    conn = get_connection(require_project=False)
    output(storage_ops.reveal_in_storage(conn, path), title="Storage Reveal")


@app.command("import-subclip")
@handle_errors
def import_subclip(
    path: str = typer.Argument(..., help="Source media path"),
    start_frame: int = typer.Option(..., "--start-frame", help="Source start frame"),
    end_frame: int = typer.Option(..., "--end-frame", help="Source end frame"),
):
    """Import a source subclip using DaVinci Resolve dict import options."""
    enforce_mutation_policy("storage.import_subclip", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would import subclip '{path}' frames {start_frame}-{end_frame}.")
        return
    conn = get_connection(require_project=True)
    output(storage_ops.import_subclip(conn, path, start_frame, end_frame), title="Import Subclip")


@app.command("import-sequence")
@handle_errors
def import_sequence(
    pattern: str = typer.Argument(..., help="Image sequence path/pattern"),
    start_index: int | None = typer.Option(None, "--start-index", help="First sequence index"),
    end_index: int | None = typer.Option(None, "--end-index", help="Last sequence index"),
):
    """Import an image sequence using DaVinci Resolve dict import options."""
    enforce_mutation_policy("storage.import_sequence", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would import image sequence '{pattern}'.")
        return
    conn = get_connection(require_project=True)
    output(storage_ops.import_sequence(conn, pattern, start_index, end_index), title="Import Sequence")


matte_app = typer.Typer(help="Storage matte import operations.")
app.add_typer(matte_app, name="matte")


@matte_app.command("add")
@handle_errors
def matte_add(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
    paths: list[str] = typer.Argument(..., help="Matte file paths"),
    eye: str | None = typer.Option(None, "--eye", help="Stereo eye: left or right"),
):
    """Add matte files to a Media Pool clip."""
    enforce_mutation_policy("storage.matte.add", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would add {len(paths)} matte file(s) to '{clip}'.")
        return
    conn = get_connection(require_project=True)
    output(storage_ops.add_clip_mattes(conn, clip, paths, eye=eye), title="Clip Mattes")


@matte_app.command("timeline-add")
@handle_errors
def matte_timeline_add(
    paths: list[str] = typer.Argument(..., help="Timeline matte file paths"),
):
    """Add timeline matte files to the Media Pool."""
    enforce_mutation_policy("storage.matte.timeline_add", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would add {len(paths)} timeline matte file(s).")
        return
    output(storage_ops.add_timeline_mattes_isolated(paths), title="Timeline Mattes")
