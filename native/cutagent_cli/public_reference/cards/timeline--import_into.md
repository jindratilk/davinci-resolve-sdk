# `timeline import-into`

Syntax: `cutagent timeline import-into FILE_PATH [--offset-tc VALUE] [--source-clips-path VALUE] [--options-json VALUE]`

## Search terms

- import into current timeline
- merge timeline interchange content
- insertWithOffset option
- sourceClipsPath option
- insertAdditionalTracks false
- timeline import options JSON

## What it does

Import timeline content into the active timeline.

## Do not use when

Do not use this command to create a separate imported timeline. Use `timeline import` for that project-level workflow.
This can merge content into existing tracks and create overlaps.
The command does not enumerate added tracks/items, media links, timing, or conflicts after import.

## Preflight and readback

Before execution, checkpoint/save the project; inspect the active timeline, locks, track layout, record range, media paths, and the interchange file.
It does not inspect files, validate option keys/value types, enforce the offset/additional-track constraint, or show the merged options.
After execution, compare timeline track/item inventories and timing against the checkpoint; inspect media relinking, overlaps, transitions, audio mapping, frame rate/timecode, and added tracks. Undo or restore if the import merged content differently than intended.

## Public arguments and options

- `FILE_PATH` (required) — Timeline import file
- `--offset-tc` (optional) — Insert with timeline offset timecode
- `--source-clips-path` (optional) — Source clips path
- `--options-json` (optional) — Additional import options as JSON

## Boundaries and gotchas

- An active timeline is required.
- The command does not trim, expand `~`, absolutize, canonicalize, or preflight the import file.
- It does not validate file existence, readability, size, extension, or content.
- `--options-json` is parsed before the dry-run branch.
- Decoded options must be a JSON object.
- Dry-run returns only a generic message containing the file path.
- It does not verify added item count, track count, placement, media links, or pixels.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline import-into --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
