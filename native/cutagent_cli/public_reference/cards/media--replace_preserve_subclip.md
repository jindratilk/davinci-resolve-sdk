# `media replace-preserve-subclip`

Syntax: `cutagent media replace-preserve-subclip CLIP PATH`

## Search terms

- replace source preserving subclip
- swap media under subclip
- keep subclip definition while relinking source
- change source without flattening subclip bounds
- restore original source to subclip

## What it does

Replace a clip while preserving subclip metadata.

## Do not use when

Use ordinary `media replace` for a normal source item with no subclip definition to preserve.

## Preflight and readback

Prove the target is actually a subclip and record its subclip in/out definition, source path, duration, Media Pool ID, standard metadata, third-party metadata, markers, source marks, and timeline uses. Checkpoint the project.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name
- `PATH` (required) — Replacement media path

## Boundaries and gotchas

- Different source stream/timecode/duration can still affect timeline uses and subclip validity. “Preserve” does not mean media compatibility has been checked.

## Examples

- `cutagent media replace-preserve-subclip --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
