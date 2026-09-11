# `layout export`

Syntax: `cutagent layout export NAME PATH`

## Search terms

- export DaVinci Resolve layout preset
- save workspace layout to file
- layout preset drfx
- overwrite layout export
- embedded layout export unsupported
- missing layout preset export
- layout recovery artifact

## What it does

Export a layout preset to file.

## Do not use when

Do not rely on dry-run to prove that the named preset exists, that the destination is writable, or that DaVinci Resolve can export it.
Do not treat an arbitrary suffix as format conversion.
Do not use this to back up projects, timelines, media, Fusion compositions, render presets, or application preferences outside the selected UI layout preset.

## Preflight and readback

Run global dry-run and confirm the normalized name and expanded path; remember that dry-run does not create directories or contact DaVinci Resolve.
Preserve the export until that round trip succeeds.
After temporary testing, remove only the uniquely named test artifacts and independently confirm unrelated presets and files remain.

## Public arguments and options

- `NAME` (required) — Layout preset name
- `PATH` (required) — Export path

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent layout export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
