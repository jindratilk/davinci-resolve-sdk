# `color gallery album switch`

Syntax: `cutagent color gallery album switch ALBUM`

## Search terms

- switch gallery album
- change current Color gallery folder
- open another still collection
- target album for still commands

## What it does

Switch current gallery album.

## Do not use when

Pass `--album` directly to a still list/import/export/apply command when you want an operation to be independent of mutable UI state. Use `album current` for readback only and PowerGrade-specific selection mechanisms for PowerGrade albums. Do not use an index copied from an older list after album creation/reordering.

## Preflight and readback

List albums immediately before switching and choose an unambiguous selector. Dry-run records the selector but intentionally leaves it unresolved.

## Public arguments and options

- `ALBUM` (required) — Album name or 1-based index

## Boundaries and gotchas

- Numeric selectors are one-based.
- Name matching is exact first and case-insensitive second.
- Duplicate/case-variant names resolve to the first match in album order.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color gallery album switch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
