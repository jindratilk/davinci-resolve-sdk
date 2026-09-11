# `media list`

Syntax: `cutagent media list [--recursive] [--kind VALUE] [--include-generated]`

## Search terms

- list Media Pool clips
- show current bin contents
- inventory imported media
- list timelines in Media Pool
- browse Media Pool folder
- find source paths in bin
- list non-generated assets
- recursively list media bins
- inspect clip kinds

## What it does

List clips in the current media pool folder.

## Do not use when

Use `media search` when the item may be outside the current folder subtree or when matching by name fragment. Do not use this to enumerate timeline items/tracks; timeline entries appearing in the Media Pool are project timeline objects, not the clips placed within them.

## Preflight and readback

Run the narrow default list for local context, then add `--recursive` only when subfolders are intended; apply `--kind` and generated filtering before matching a target.

## Public arguments and options

- `--recursive/-r` (optional, default: `false`) — Include subfolders
- `--kind` (optional) — Filter by kind: media, timeline, subtitle
- `--include-generated/--exclude-generated` (optional, default: `true`)

## Boundaries and gotchas

- `--kind` accepts only `media`, `timeline`, or `subtitle`.
- Timeline Media Pool entries have no source path and can report `0x0` or other properties that do not mirror timeline settings exactly.

## Examples

- `cutagent media list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
