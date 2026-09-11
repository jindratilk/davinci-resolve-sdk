# `media growing-file monitor`

Syntax: `cutagent media growing-file monitor CLIP`

## Search terms

- monitor growing media file
- edit while ingest
- follow file that is still being written
- refresh recording duration in Media Pool
- start monitoring active capture
- edit incomplete recording

## What it does

Enable growing-file monitoring for a clip.

## Do not use when

Use media import when the recording is not already represented by a Media Pool item.

## Preflight and readback

Confirm the exact item and source path with `media info`; inspect storage to establish that the container is genuinely being written and supports growing-file use. Record current duration/end frame and any timeline use. A static `monitoring: true` response is not evidence that the source grew or that appended essence is usable.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name

## Boundaries and gotchas

- Monitoring state is attached to the Media Pool object; the command does not create a new object or independently configure each timeline occurrence.
- Agents must verify progressive readback on the user's real recorder/container before promising edit-while-ingest behavior.

## DaVinci Resolve editions

Agents must verify progressive readback on the user's real recorder/container before promising edit-while-ingest behavior. - Studio/Free parity was not established.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent media growing-file monitor --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
