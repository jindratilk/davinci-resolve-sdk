# `clip link`

Syntax: `cutagent clip link CLIPS...`

## Search terms

- link video and audio clips
- make clips move together
- pair external audio with video
- link timeline items
- reconnect unlinked picture and sound
- group clip selection behavior
- bind video occurrence to audio occurrence
- create DaVinci Resolve clip link

## What it does

Link timeline clips.

## Do not use when

Use synchronization commands when picture and sound are not already aligned; link preserves their existing positions and offsets. Use compound/multicam creation when the user needs a new container or camera angles. Do not use this command merely to inspect relationships; use `clip linked list`.

## Preflight and readback

Align/sync items before linking, because this command performs no alignment.

## Public arguments and options

- `CLIPS` (required, repeatable) — Clip names to link

## Boundaries and gotchas

- `--dry-run` is dangerously ineffective.
- Duplicate names can link unintended occurrences; there is no track/frame selector or occurrence index.
- Link does not imply equal boundaries.

## Stable public error codes

- `MISSING_ARGUMENT`

## Examples

- `cutagent clip link --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
