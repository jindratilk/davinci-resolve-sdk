"""Compatibility facade for this legacy public module."""
from __future__ import annotations

import sys

from . import _timeline_ops_facade as _impl

_PUBLIC_NAME = __name__.rpartition(".")[2]
sys.modules[__name__] = _impl
setattr(sys.modules[__package__], _PUBLIC_NAME, _impl)
