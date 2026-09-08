"""Asset resolution commands."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import typer

from ..connection import get_connection
from ..core.asset_resolver import resolve_asset_candidates
from ..errors import AssetNotFound, ValidationError, handle_errors
from ..output import output, set_capability_context, set_execution_engine, set_recoverability, set_verification_status

app = typer.Typer(help="Read-only asset resolution helpers.")

_ARTIFACT_SUFFIXES = {".setting", ".png", ".jpg", ".jpeg", ".mp4", ".mov", ".gif", ".json", ".md"}


def _artifact_role(path: Path) -> str:
    lower = path.name.lower()
    parent = path.parent.name.lower()
    if path.suffix.lower() == ".setting":
        if "final" in lower:
            return "final_setting"
        if "applied" in lower:
            return "applied_setting"
        return "setting"
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        if "contact" in lower or "sheet" in lower:
            return "contact_sheet"
        if "frame" in parent or "frame" in lower or "verify" in lower or re.search(r"(?:^|_)\d+f(?:_|\.|$)", lower):
            return "verification_frame"
        return "image"
    if path.suffix.lower() in {".mp4", ".mov", ".gif"}:
        return "preview"
    return "artifact"


def _artifact_row(path: Path, root: Path) -> dict:
    try:
        stat = path.stat()
    except OSError:
        stat = None
    try:
        relative = str(path.relative_to(Path.cwd()))
    except ValueError:
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            relative = str(path)
    return {
        "path": str(path),
        "visual_check_path": relative,
        "name": path.name,
        "suffix": path.suffix.lower(),
        "role": _artifact_role(path),
        "bytes": stat.st_size if stat else None,
        "mtime": stat.st_mtime if stat else None,
    }


def _scan_artifacts(roots: list[str], *, limit: int) -> dict:
    resolved_roots: list[Path] = []
    for raw in roots:
        root = Path(str(raw)).expanduser()
        if not root.is_absolute():
            root = Path.cwd() / root
        root = root.resolve(strict=False)
        if root.is_dir():
            resolved_roots.append(root)
    rows: list[dict] = []
    for root in resolved_roots:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in _ARTIFACT_SUFFIXES:
                rows.append(_artifact_row(path, root))
    rows.sort(key=lambda row: float(row.get("mtime") or 0), reverse=True)
    if limit > 0:
        rows = rows[:limit]
    by_role: dict[str, list[dict]] = {}
    for row in rows:
        by_role.setdefault(str(row["role"]), []).append(row)
    return {
        "roots": [str(root) for root in resolved_roots],
        "count": len(rows),
        "latest": rows,
        "by_role": by_role,
    }


def _load_candidates(candidates: Optional[str], candidates_file: Optional[str]) -> list[dict]:
    if bool(candidates) == bool(candidates_file):
        raise ValidationError(
            "Specify exactly one candidate source.",
            details={"required_one_of": ["--candidates", "--candidates-file"]},
        )

    raw = str(candidates_file if candidates_file else candidates)
    if candidates_file:
        try:
            text = Path(raw).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise ValidationError("Candidate file could not be read.", details={"path": raw, "error": str(exc)}) from exc
    else:
        text = raw
        stripped = raw.strip()
        if not stripped.startswith(("[", "{")):
            path = Path(stripped).expanduser()
            if path.is_file():
                text = path.read_text(encoding="utf-8")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Candidates must be valid JSON.",
            details={"line": exc.lineno, "column": exc.colno, "message": exc.msg},
        ) from exc
    if not isinstance(payload, list):
        raise ValidationError("Candidates JSON must be an array.", details={"type": type(payload).__name__})
    return payload


def _needs_resolve_connection(candidates: list[dict]) -> bool:
    return any(isinstance(candidate, dict) and candidate.get("type") in {"media", "custom-media"} for candidate in candidates)


@app.command("resolve")
@handle_errors
def resolve(
    candidates: Optional[str] = typer.Option(None, "--candidates", help="Inline candidates JSON, or a path to a JSON file"),
    candidates_file: Optional[str] = typer.Option(None, "--candidates-file", help="Path to candidates JSON"),
    require: bool = typer.Option(False, "--require", help="Fail with ASSET_NOT_FOUND when no candidate resolves"),
    mode: str = typer.Option("first", "--mode", help="Resolution mode: first|all"),
):
    """Resolve the first available file, template, media, or custom-media fallback asset."""
    set_capability_context("asset.resolve", "supported")
    set_execution_engine("api_native")
    set_verification_status("not_requested")
    set_recoverability("manual")
    loaded_candidates = _load_candidates(candidates, candidates_file)
    conn = get_connection(require_project=True) if _needs_resolve_connection(loaded_candidates) else None
    payload = resolve_asset_candidates(conn, loaded_candidates, require=require, mode=mode)
    if require and payload.get("selected") is None:
        raise AssetNotFound("No candidate asset resolved.", details={"attempts": payload.get("attempts", [])})
    output(payload, title="Asset Resolve")


@app.command("artifact-index")
@handle_errors
def artifact_index(
    root: list[str] = typer.Option(["artifacts"], "--root", help="Artifact root directory; repeatable"),
    limit: int = typer.Option(80, "--limit", help="Maximum rows to return; <=0 means all"),
):
    """List recent local artifacts so agents can find exported frames/settings."""
    set_capability_context("asset.artifact_index", "supported")
    set_execution_engine("api_native")
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(_scan_artifacts(root, limit=limit), title="Artifact Index")
