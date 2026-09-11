# `color gallery still list`

Syntax: `cutagent color gallery still list [--album VALUE]`

## Search terms

- list gallery stills
- show grades in still album
- find still index by label
- inspect Color gallery contents
- choose still for apply or export
- list DRX looks in album

## What it does

List stills in selected album.

## Do not use when

Do not treat an index from an old listing as persistent: grab/import/delete can immediately renumber stills.

## Preflight and readback

Use the fresh list to choose an index/unique label before apply/export/delete/label. After any still mutation, rerun the list and compare count, order, and labels; this is especially important because import itself does not verify a count change.

## Public arguments and options

- `--album` (optional) — Album name or 1-based index

## Boundaries and gotchas

- Indices are one-based positions, not stable still IDs.
- A label selector elsewhere resolves exact first, then case-insensitive, and returns the first match.
- This list provides no extra identifier for duplicate labels.
- Rows do not distinguish grabbed image stills from DRX-only imports.
- The command lists ordinary still albums only; it does not expose PowerGrade stills.

## Examples

- `cutagent color gallery still list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
