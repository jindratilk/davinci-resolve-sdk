# `timeline track add`

Syntax: `cutagent timeline track add TRACK_TYPE [--subtype VALUE] [--index VALUE]`

## Search terms

- add timeline track
- create video track
- create audio track
- create subtitle track
- audio track subtype
- timeline track management

## What it does

Add a new track.

## Do not use when

Do not use this to rename, enable, lock, configure, or populate a track; those are separate operations.
The CLI does not validate subtype names or index bounds.
Do not interpret a successful command as structural readback.

## Preflight and readback

After execution, list tracks again and verify count, order, type, index, name, subtype, routing, and downstream index references in DaVinci Resolve. If the structure differs, repair it explicitly before issuing commands that address tracks by index.

## Public arguments and options

- `TRACK_TYPE` (required) — Track type: video, audio, subtitle
- `--subtype` (optional) — Optional audio subtype
- `--index` (optional) — Optional insertion index

## Boundaries and gotchas

- `--subtype` is optional and is not normalized, trimmed, or checked against an allowlist.
- DaVinci Resolve therefore decides whether zero, negative, out-of-range, or otherwise unsupported indexes fail or behave unexpectedly.
- The command does not save the project.
- Critically, dry-run also returns before type, subtype, or index validation.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline track add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
