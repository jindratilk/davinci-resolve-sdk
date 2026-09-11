# `timeline thumbnail`

Syntax: `cutagent timeline thumbnail [--output VALUE]`

## Search terms

- export timeline thumbnail
- save current frame still
- playhead image export
- DaVinci Resolve thumbnail PNG
- current clip preview image
- color page still workaround

## What it does

Export thumbnail of current clip under playhead.

## Do not use when

Do not use this to capture a named clip, timeline, or frame independently of current UI state; the command has no target selector and exports whatever frame is under the active playhead.
Do not use it for a requested frame sequence, contact sheet, or preview video; use the dedicated frame-export or preview-export commands.

## Preflight and readback

Inspect or move any existing destination file first because there is no overwrite guard.

## Public arguments and options

- `--output/-o` (optional, default: `"thumbnail.png"`) — Output file path

## Boundaries and gotchas

- JPEG detection reports only `format: jpeg`; width and height remain null.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline thumbnail --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
