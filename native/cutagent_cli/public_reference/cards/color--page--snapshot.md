# `color page snapshot`

Syntax: `cutagent color page snapshot [DB_PATH] [--clip VALUE]`

## Search terms

- inspect every Color version
- decode Color page node params
- inspect curves HDR CST and Color Warper payloads
- find duplicate clip grade rows

## What it does

Capture all color grade data from a project checkpoint for analysis.

## Do not use when

Do not treat the first same-name row/version as the current timeline clip or active Color version because the response contains neither active-version markers nor track/timeline placement.

## Preflight and readback

Record the intended timeline item's unique identity and active Color version separately. After reading, group by clip `id`, inspect every linked version and per-version `error`, and compare explicit params rather than assuming omitted defaults.

## Public arguments and options

- `DB_PATH` (optional)
- `--clip` (optional) — Filter by clip name

## Boundaries and gotchas

- There is no `active: true` marker, guaranteed version order, track, timeline, start or duration, so it cannot identify the currently displayed grade by itself.
- Cloud/PostgreSQL libraries, inaccessible paths, and non-Disk projects cannot be auto-detected by this route.
- `--dry-run` has no special branch.

## Examples

- `cutagent color page snapshot --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
