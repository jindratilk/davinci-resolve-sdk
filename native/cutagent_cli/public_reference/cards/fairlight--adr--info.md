# `fairlight adr info`

Syntax: `cutagent fairlight adr info [--limit VALUE]`

## Search terms

- inspect ADR storage
- inspect AutoCue settings
- find ADR take tables
- diagnose unavailable ADR cue list

## What it does

Runs the public `fairlight adr info` CutAgent command.

## Do not use when

Use a manual Fairlight ADR panel or exported cue sheet when guaranteed semantic cue data—cue ID, actor, prompt, in/out, take selection/rating—is required. Use ordinary clip/track commands after ADR takes have become timeline media.

## Preflight and readback

Before running, require a saved local Disk project and identify the expected project/timeline.

## Public arguments and options

- `--limit` (optional, default: `20`)

## Boundaries and gotchas

- Cloud/PostgreSQL project libraries and unsaved/ambiguous projects are not valid evidence sources.
- It does not mean cue rows exist.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight adr info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
