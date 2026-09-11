# `multicam verdict-list`

Syntax: `cutagent multicam verdict-list [--registry-path VALUE]`

## Search terms

- list multicam UI verdicts
- manual DaVinci Resolve verification registry
- multicam family UI evidence
- repo manual verdict rules
- inspect verdict rule IDs
- multicam regex registry
- verdict registry path

## What it does

List multicam review notes for multicam families.

## Do not use when

Do not use the default registry for experiments. Supply an isolated path unless intentionally reading the repository-owned evidence.
Do not infer that every matching name has the same UI behavior without also checking angle count and the evidence notes/date.
Do not edit malformed registry JSON by hand without preserving its evidence. Listing fails closed on invalid structure, status, date, or entry shape.

## Preflight and readback

Prefer an explicit absolute path for tests.
After listing, inspect the resolved path, rule IDs, statuses, angle filters, regexes, dates, labels, and notes. Correlate any applicable rule with `multicam inspect` and current real DaVinci Resolve UI/render evidence.
Use the exact rule ID for updates or removal. An empty result means no manual verdict is recorded, not that the multicam is rejected or unsupported.

## Public arguments and options

- `--registry-path` (optional) — Optional manual UI verdict registry path

## Boundaries and gotchas

- The root must be an object and `verdicts` must be a list.
- Every entry must be an object with at least one nonempty clip-name pattern.
- Global dry-run does not change behavior because this command is read-only.

## Examples

- `cutagent multicam verdict-list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
