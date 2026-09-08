"""Worker process for timeline matte imports.

This module is intentionally tiny: it performs the native DaVinci Resolve API call and
writes a JSON status file for the parent CLI process. Some DaVinci Resolve beta builds
can crash during native scripting proxy cleanup after returning success; keeping
that risk in a child process prevents the public CLI from emitting a misleading
successful envelope and then exiting with SIGSEGV.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .connection import get_connection
from .errors import CLIError
from .core import storage_ops


def _write_status(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        sys.stderr.write("usage: python -m cutagent_cli._timeline_matte_worker STATUS_JSON PATHS_JSON\n")
        return 2

    status_path = Path(args[0])
    try:
        paths = json.loads(args[1])
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            raise ValueError("PATHS_JSON must be a JSON array of strings.")

        conn = get_connection(require_project=True)
        data = storage_ops.add_timeline_mattes(conn, paths)
        _write_status(status_path, {"ok": True, "data": data})
        return 0
    except CLIError as exc:
        _write_status(
            status_path,
            {
                "ok": False,
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                },
            },
        )
        return exc.exit_code
    except Exception as exc:
        _write_status(
            status_path,
            {
                "ok": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc) or exc.__class__.__name__,
                    "details": {"type": exc.__class__.__name__},
                },
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
