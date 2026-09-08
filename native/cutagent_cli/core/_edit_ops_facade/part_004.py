from __future__ import annotations


# ---------------------------------------------------------------------------
# From-EDL
# ---------------------------------------------------------------------------

def _read_edl_title(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped.upper().startswith("TITLE:"):
                    title = stripped.split(":", 1)[1].strip()
                    return title or None
    except OSError:
        return None
    return None


def validate_edl_import_file(path: str) -> Dict[str, Any]:
    """Validate an EDL import path and return deterministic naming metadata."""
    normalized_path = os.path.abspath(os.path.expanduser(str(path or "").strip()))
    if not str(path or "").strip():
        raise ValidationError(
            "EDL path must not be empty.",
            details={"path": path},
            recoverability="not_applicable",
        )
    if not os.path.exists(normalized_path):
        raise ValidationError(
            "EDL file does not exist.",
            details={"path": normalized_path},
            recoverability="not_applicable",
        )
    if not os.path.isfile(normalized_path):
        raise ValidationError(
            "EDL path must be a file.",
            details={"path": normalized_path},
            recoverability="not_applicable",
        )
    if os.path.splitext(normalized_path)[1].lower() != ".edl":
        raise ValidationError(
            "EDL import requires a .edl file.",
            details={"path": normalized_path},
            recoverability="not_applicable",
        )

    from ..core import edl_ops

    try:
        events = edl_ops.parse_edl(normalized_path)
    except Exception as exc:
        raise ValidationError(
            "EDL file could not be parsed.",
            details={"path": normalized_path, "error": str(exc)},
            recoverability="not_applicable",
        ) from exc
    title = _read_edl_title(normalized_path)
    if not events:
        raise ValidationError(
            "EDL file contains no edit events.",
            details={"path": normalized_path, "title": title},
            recoverability="not_applicable",
        )
    expected_name = os.path.splitext(os.path.basename(normalized_path))[0]
    return {
        "path": normalized_path,
        "edl_title": title,
        "event_count": len(events),
        "expected_timeline_name": expected_name,
        "timeline_name_source": "file_basename",
        "edl_title_honored": title == expected_name if title else None,
    }


def import_edl(
    conn, path: str, *, expected_timeline_name: str | None = None
) -> Dict[str, Any]:
    """Import an EDL file as a new timeline."""
    from ..core import timeline_ops

    preflight = validate_edl_import_file(path)
    if expected_timeline_name is not None:
        available_name = timeline_ops._unique_timeline_import_name(conn, preflight["path"])
        if (
            preflight["expected_timeline_name"] != expected_timeline_name
            or available_name != expected_timeline_name
        ):
            raise ValidationError(
                "Prepared EDL import name is unavailable or does not match its managed artifact.",
                details={
                    "expected_timeline_name": expected_timeline_name,
                    "artifact_timeline_name": preflight["expected_timeline_name"],
                    "available_timeline_name": available_name,
                },
                recoverability="not_applicable",
            )
    tl = timeline_ops.import_timeline(conn, preflight["path"])
    timeline_name = tl.GetName() if hasattr(tl, "GetName") else ""
    verification = _verify_imported_timeline_readback(conn, tl, timeline_name)
    return {
        "timeline": timeline_name,
        "path": preflight["path"],
        "edl_title": preflight["edl_title"],
        "expected_timeline_name": preflight["expected_timeline_name"],
        "timeline_name_source": preflight["timeline_name_source"],
        "edl_title_honored": timeline_name == preflight["edl_title"] if preflight["edl_title"] else None,
        "event_count": preflight["event_count"],
        "verification": verification,
    }
