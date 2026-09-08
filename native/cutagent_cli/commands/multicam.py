"""Canonical multicam command family compatibility facade."""
from __future__ import annotations

from pathlib import Path as _FacadePath

_PARTS = (
    'part_001.py',
    'part_002.py',
)
_SHARD_DIR = _FacadePath(__file__).with_name("_multicam_command")


def _facade_exec_part(filename: str) -> None:
    path = _SHARD_DIR / filename
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    exec(code, globals())


for _facade_part in _PARTS:
    _facade_exec_part(_facade_part)


del _facade_part, _facade_exec_part, _FacadePath
