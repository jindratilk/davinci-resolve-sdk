# `color gallery still apply`

Syntax: `cutagent color gallery still apply SELECTOR [--clip VALUE] [--mode VALUE] [--album VALUE]`

## Search terms

- apply gallery still grade
- paste saved still look to clip
- copy gallery grade onto shot
- apply album still by label
- transfer still DRX to timeline item
- use reference still grade on clip

## What it does

Apply still grade to a clip.

## Do not use when

Use `color grade-apply` when a DRX file already exists, `color grade-copy` for another clip’s active grade in the same Disk project, and `gallery still export` when the task is only to save the still. Do not use an image-only still as evidence that an editable grade exists; the apply route specifically needs a successful DRX export. Choose modes 1/2 only for keyframed grades whose timing domain is understood.

## Preflight and readback

List the album, preserve the target’s existing grade/version, inspect the still label and choose the alignment mode, then dry-run with explicit album and clip.

## Public arguments and options

- `SELECTOR` (required) — Still selector (index or label)
- `--clip` (optional) — Target clip name
- `--mode` (optional, default: `0`) — Grade mode: 0, 1, 2
- `--album` (optional) — Album name or 1-based index

## Boundaries and gotchas

- Dry-run validates mode/strings but returns `resolved: false`; it does not prove the album, still, clip, or DRX export is available.
- Label selection is exact then case-insensitive and chooses the first duplicate.
- Numeric strings are always treated as one-based indices.
- Omitting `--clip` uses current timeline clip; omitting `--album` uses current Gallery album.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color gallery still apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
