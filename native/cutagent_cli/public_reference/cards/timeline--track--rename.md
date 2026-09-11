# `timeline track rename`

Syntax: `cutagent timeline track rename TRACK_TYPE INDEX NAME`

## Search terms

- rename timeline track
- set video track name
- set audio track name
- set subtitle track name
- label timeline tracks
- timeline track management

## What it does

Rename a track.

## Do not use when

Do not use this to change track type, subtype, routing, enabled state, lock state, or index. It changes only the name.
Do not use global `--dry-run` as a preview.
Do not rely on success as name readback.

## Preflight and readback

Before execution, activate and save the intended timeline; freshly list tracks; verify the exact type, one-based index, current name, and desired non-empty name; quote names containing spaces or shell-sensitive characters; and avoid a normal dry-run.
After execution, list tracks again and require the expected name on the same intended track.

## Public arguments and options

- `TRACK_TYPE` (required) — video, audio, subtitle
- `INDEX` (required) — Track index
- `NAME` (required) — New name

## Boundaries and gotchas

- It lowercases the type but does not trim whitespace.
- Name is required syntactically but is not trimmed or checked for emptiness.
- It cannot distinguish an actual rename from an accepted no-op.
- It does not save the project.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent timeline track rename --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
