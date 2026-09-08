"""Internal implementation shards for the compatibility facade."""
from __future__ import annotations

import importlib.machinery as _facade_machinery
import sys as _facade_sys
from pathlib import Path as _FacadePath

_ORIGINAL_MODULE = 'cutagent_cli.commands.clip'
_ORIGINAL_PACKAGE = 'cutagent_cli.commands'
_ORIGINAL_BASENAME = 'clip.py'
_PARTS = (
    'part_001.py',
    'part_002.py',
    'part_003.py',
)

_facade_module = _facade_sys.modules[__name__]
_SHARD_DIR = _FacadePath(__file__).parent
_facade_sys.modules[_ORIGINAL_MODULE] = _facade_module
setattr(_facade_sys.modules[_ORIGINAL_PACKAGE], 'clip', _facade_module)
globals()["__package__"] = _ORIGINAL_PACKAGE
globals()["__name__"] = _ORIGINAL_MODULE
globals()["__spec__"] = _facade_machinery.ModuleSpec(_ORIGINAL_MODULE, loader=None)
globals()["__file__"] = str(_SHARD_DIR.parent / _ORIGINAL_BASENAME)


def _facade_exec_part(filename: str) -> None:
    path = _SHARD_DIR / filename
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    exec(code, globals())


for _facade_part in _PARTS:
    _facade_exec_part(_facade_part)


del _facade_part, _facade_exec_part, _facade_module, _SHARD_DIR, _FacadePath, _facade_machinery, _facade_sys
