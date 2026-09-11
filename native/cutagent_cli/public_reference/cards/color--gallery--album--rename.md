# `color gallery album rename`

Syntax: `cutagent color gallery album rename ALBUM NEW_NAME`

## Search terms

- rename gallery album
- change still folder name
- relabel Color page album
- rename grade collection
- rename stills bin by index

## What it does

Rename a gallery still album.

## Do not use when

Use `gallery still label` to rename one still, `album create` for a new collection, and PowerGrade-specific album commands for PowerGrade storage. Do not use a stale index: rerun `album list` immediately before renaming, especially after album creation/reordering.

## Preflight and readback

List albums, choose an unambiguous selector, and record whether the target is current. Dry-run confirms only the literal strings. If name uniqueness matters, check for case-insensitive collisions yourself before mutation.

## Public arguments and options

- `ALBUM` (required) — Album name or 1-based index
- `NEW_NAME` (required) — New album name

## Boundaries and gotchas

- Numeric strings are always treated as one-based indices.
- An album literally named `2` cannot be selected by name through this resolver while at least two albums exist.
- Exact name matching is tried first, then case-insensitive matching.
- Renaming does not rewrite any external DRX/export filenames or references to the old name in agent workflows.

## Examples

- `cutagent color gallery album rename --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
