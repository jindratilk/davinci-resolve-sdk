# `storage import-subclip`

Syntax: `cutagent storage import-subclip PATH --start-frame VALUE --end-frame VALUE`

## Search terms

- import source subclip
- media startFrame endFrame
- bounded source media import
- source frame range
- Media Storage subclip
- partial clip ingest
- import trimmed media item

## What it does

Import a source subclip using DaVinci Resolve import options.

## Do not use when

Do not trust dry-run to validate source existence or frame ordering.
Do not use timeline-record frame numbers unless they intentionally match source-media frame coordinates.
Do not assume the imported item lands in a specific bin without making the intended Media Pool folder current.

## Preflight and readback

Before execution, inspect source metadata, total frames/timecode, choose bounds with `end > start`, and make the intended project/bin current. Capture existing bin items.
Remove an incorrect item manually.

## Public arguments and options

- `PATH` (required) — Source media path
- `--start-frame` (required) — Source start frame
- `--end-frame` (required) — Source end frame

## Boundaries and gotchas

- Exact help is `cutagent storage import-subclip PATH --start-frame N --end-frame N`.
- Both frame options are required integers.
- Dry-run does not validate `end > start`.
- CLI integer parsing still occurs before dry-run.
- It does not expose source-frame inclusivity/exclusivity or verify it.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent storage import-subclip --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
