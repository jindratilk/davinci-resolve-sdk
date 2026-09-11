# `color gallery still delete`

Syntax: `cutagent color gallery still delete SELECTOR [--album VALUE] [--force]`

## Search terms

- delete gallery still
- remove saved grade from album
- clean up Color page still
- erase captured reference still
- remove DRX look from project gallery
- delete still by label or index

## What it does

Delete one still from selected album.

## Do not use when

Do not delete by a stale index after imports/grabs/deletes; refresh the list and prefer a unique label where possible.

## Preflight and readback

In machine mode, add `--force` only after reviewing that plan.

## Public arguments and options

- `SELECTOR` (required) — Still selector (index or label)
- `--album` (optional) — Album name or 1-based index
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- Dry-run does not resolve the still/album and therefore cannot catch an out-of-range index or duplicate label.
- Index resolution is one-based and labels resolve first exact then case-insensitive.
- Duplicate labels delete the first match.
- Deleting a still does not remove temporary DRX files left by apply or files previously exported from it.

## Stable public error codes

- `CONFIRMATION_REQUIRED`

## Examples

- `cutagent color gallery still delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
