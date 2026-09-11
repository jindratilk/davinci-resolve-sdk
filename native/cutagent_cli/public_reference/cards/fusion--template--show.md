# `fusion template show`

Syntax: `cutagent fusion template show NAME`

## Search terms

- show Fusion template
- inspect raw setting text
- print .setting file
- template filename contents
- bundled template source
- Fusion placeholder source
- raw Fusion template
- template rendered JSON
- template file readback

## What it does

Check template contents.

## Do not use when

Do not use this command to locate an unknown template. Run `fusion template list` first.
Do not pass a bare name without the exact suffix.
Do not expect dry-run to avoid reading the file.

## Preflight and readback

Inspect the shown graph for placeholders, tool classes, SourceOp references, MediaOut, fonts, media paths, expressions, plugins, and frame-range assumptions. Use the structured setting commands rather than manual text inference for machine decisions.
No DaVinci Resolve cleanup is needed.

## Public arguments and options

- `NAME` (required) — Template filename

## Boundaries and gotchas

- It does not search user/system DaVinci Resolve Fusion Macros or Templates directories.
- Decode errors or permission failures are handled only by the generic error wrapper.

## Stable public error codes

- `API_CALL_FAILED`
- `FILE_NOT_FOUND`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion template show --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
