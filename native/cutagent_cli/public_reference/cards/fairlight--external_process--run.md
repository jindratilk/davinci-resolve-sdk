# `fairlight external-process run`

Syntax: `cutagent fairlight external-process run [TOOL] [--clip VALUE]`

## Search terms

- run Fairlight external process
- send clip to iZotope RX
- open audio clip in external editor
- round-trip audio from DaVinci Resolve
- launch configured waveform editor
- process clip outside Fairlight
- external audio editor handoff
- replace clip with processed audio
- RX connect round trip

## What it does

Check Fairlight external audio process availability.

## Do not use when

Use `fairlight external-process list` only to inspect configured XML entries.

## Preflight and readback

Preserve the requested tool/clip in a workflow plan and explain the boundary instead of retrying spellings. If the user chooses a manual or export-based alternative, establish separate preflight and post-import verification for that new workflow.

## Public arguments and options

- `TOOL` (optional) — Configured external audio process name
- `--clip` (optional) — Timeline clip name or item id

## Boundaries and gotchas

- `tool` and `--clip` are optional and unvalidated.
- `--dry-run` has no special success plan here.
- Retrying cannot advance the workflow.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight external-process run --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
