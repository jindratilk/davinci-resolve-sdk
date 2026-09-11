# `color gallery still export`

Syntax: `cutagent color gallery still export SELECTOR OUTPUT_PATH_OR_DIR [--format VALUE] [--album VALUE]`

## Search terms

- export gallery still
- save still grade as DRX
- export Color gallery image as PNG
- extract look from gallery album
- save selected gallery still to file

## What it does

Export one still from selected album.

## Do not use when

Use `color export-lut` to bake a clip grade into a cube, `gallery still apply` to transfer the grade to a clip, and `color grade-apply` when an existing DRX already exists. Use DRX rather than PNG/JPG when editable grade data is the goal; image exports are visual stills and cannot reconstruct the node grade. Do not request image export from a grade-only DRX import without first confirming that it has a captured image representation.

## Preflight and readback

List the exact album, choose an unambiguous selector, dry-run the absolute output path, and protect any existing file manually.

## Public arguments and options

- `SELECTOR` (required) — Still selector (index or label)
- `OUTPUT_PATH_OR_DIR` (required) — Output path or directory
- `--format` (optional, default: `"drx"`) — drx|png|jpg
- `--album` (optional) — Album name or 1-based index

## Boundaries and gotchas

- Dry-run does not resolve the still/album or create the parent; it only validates format/strings and absolutizes the requested path.
- Only `drx`, `png`, and `jpg` are accepted.

## Examples

- `cutagent color gallery still export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
