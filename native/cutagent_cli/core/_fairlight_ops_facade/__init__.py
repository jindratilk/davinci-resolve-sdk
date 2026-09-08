"""Internal implementation shards for the compatibility facade."""
from __future__ import annotations

import importlib.machinery as _facade_machinery
import importlib as _facade_importlib
import sys as _facade_sys
from pathlib import Path as _FacadePath

_ORIGINAL_MODULE = 'cutagent_cli.core.fairlight_ops'
_ORIGINAL_PACKAGE = 'cutagent_cli.core'
_ORIGINAL_BASENAME = 'fairlight_ops.py'
_PARTS = (
    'part_001.py',
    'part_002.py',
    'part_004.py',
)
_AUDIO_BATCH_EXPORTS = (
    'inspect_sdk_fairlight_plan_clip_state',
    '_resolve_audio_gain_batch_targets',
    '_audio_gain_batch_writer',
    '_verify_audio_gain_batch',
    'preview_audio_gain_batch',
    'apply_audio_gain_batch',
    '_audio_pan_item_payload',
    '_resolve_audio_pan_batch_targets',
    '_audio_pan_batch_writer',
    '_verify_audio_pan_batch',
    'preview_audio_pan_batch',
    'apply_audio_pan_batch',
    '_parse_fade_duration_ref',
    '_fade_operation_label',
    '_fade_duration_frames_for_entry',
    'normalize_audio_fade_batch_selectors',
    '_audio_fade_target_payload',
    '_resolve_audio_fade_batch_targets',
    '_adjacent_same_track_audio_item_ids',
    '_plan_audio_fade_batch',
    '_missing_audio_fade_selector_skips',
    '_audio_fade_batch_counts',
    '_unexpected_audio_fade_skips',
    '_raise_incomplete_audio_fade_batch',
    '_audio_fade_batch_writer',
    '_verify_audio_fade_batch',
    '_crossfade_base_payload',
    '_crossfade_edge_frames',
    '_plan_audio_crossfade_batch',
    '_audio_crossfade_batch_writer',
    '_verify_audio_crossfade_batch',
    'preview_audio_crossfade_batch',
    'apply_audio_crossfade_batch',
    '_preview_audio_fade_batch',
    'preview_audio_fade_in_batch',
    'preview_audio_fade_out_batch',
    '_apply_audio_fade_batch',
    'apply_audio_fade_in_batch',
    'apply_audio_fade_out_batch',
    'patch_audio_track_db_subtypes',
)

_facade_module = _facade_sys.modules[__name__]
_SHARD_DIR = _FacadePath(__file__).parent
_facade_sys.modules[_ORIGINAL_MODULE] = _facade_module
setattr(_facade_sys.modules[_ORIGINAL_PACKAGE], 'fairlight_ops', _facade_module)
globals()["__package__"] = _ORIGINAL_PACKAGE
globals()["__name__"] = _ORIGINAL_MODULE
globals()["__spec__"] = _facade_machinery.ModuleSpec(_ORIGINAL_MODULE, loader=None)
globals()["__file__"] = str(_SHARD_DIR.parent / _ORIGINAL_BASENAME)


def _facade_exec_part(filename: str) -> None:
    path = _SHARD_DIR / filename
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    exec(code, globals())


for _facade_part in _PARTS[:2]:
    _facade_exec_part(_facade_part)

_audio_batches = _facade_importlib.import_module(
    'cutagent_cli.core._fairlight_ops_facade.audio_batches'
)
_audio_batches._bind_facade(_facade_module)
for _audio_batch_export in _AUDIO_BATCH_EXPORTS:
    _audio_batch_value = getattr(_audio_batches, _audio_batch_export)
    _audio_batch_value.__module__ = _ORIGINAL_MODULE
    globals()[_audio_batch_export] = _audio_batch_value

_facade_exec_part(_PARTS[2])

del _audio_batch_export, _audio_batch_value, _audio_batches, _facade_part, _facade_exec_part, _facade_module, _SHARD_DIR, _FacadePath, _facade_importlib, _facade_machinery, _facade_sys
