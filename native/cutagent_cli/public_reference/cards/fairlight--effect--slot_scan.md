# `fairlight effect slot-scan`

Syntax: `cutagent fairlight effect slot-scan [--limit VALUE]`

## Search terms

- find clip FX payloads
- locate Fairlight effect candidates
- distinguish mixer tokens from active clip effects
- audit BMD plugin IDs in timeline
- find which audio clips have effects

## What it does

Check Fairlight effect slot candidates.

## Do not use when

Do not use this command for a concise effect chain on one known clip; use `fairlight effect list --clip NAME`. Do not use this scan to infer parameter values; follow a recognized clip entry with `fairlight effect params EFFECT --clip NAME`.

## Preflight and readback

Confirm the exact active project and timeline, then save the project if recently changed effects must be visible on disk.

## Public arguments and options

- `--limit` (optional, default: `100`) — Maximum candidates per source bucket to return

## Boundaries and gotchas

- `--limit` is per source bucket.
- Those baseline entries must not be reported as applied effects.

## Examples

- `cutagent fairlight effect slot-scan --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
