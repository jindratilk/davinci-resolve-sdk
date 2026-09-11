# `timeline output-blanking set`

Syntax: `cutagent timeline output-blanking set [--top VALUE] [--bottom VALUE] [--left VALUE] [--right VALUE] [--item-id VALUE] [--use-timeline]`

## Search terms

- output blanking
- image bounds
- letterbox
- clip blanking inheritance

## What it does

Set all four pixel edges, and explicitly select clip inheritance.

## Do not use when

Do not use this as a crop or scale operation. Titles and generators may not provide clip-level blanking.

## Preflight and readback

An inherited clip returns no active clip override and reports effective timeline bounds. Verify the returned state and preserve unrelated clips.

## Public arguments and options

- `--top` (optional) — Top blanking in pixels
- `--bottom` (optional) — Bottom blanking in pixels
- `--left` (optional) — Left blanking in pixels
- `--right` (optional) — Right blanking in pixels
- `--item-id` (optional) — Exact video timeline item ID; omit for timeline blanking
- `--use-timeline/--use-clip` (optional) — Use timeline blanking or the stored clip override; mutually exclusive with edge values

## Boundaries and gotchas

- --use-timeline and --use-clip require an exact --item-id and cannot be combined with edge values.

## Examples

- `cutagent timeline output-blanking set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
