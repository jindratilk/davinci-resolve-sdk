# `render export-file`

Syntax: `cutagent render export-file OUTPUT_PATH --format VALUE --codec VALUE [--width VALUE] [--height VALUE] [--fps VALUE] [--video] [--audio]`

## Search terms

- export timeline file
- render and validate file
- exact output file
- file delivery

## What it does

Render one exact timeline output with complete validation.

## Do not use when

Do not use this lower-level command as the contract for a durable SDK operation.
A terminal queue status by itself is insufficient.

## Preflight and readback

Supply width and height together.

## Public arguments and options

- `OUTPUT_PATH` (required) — Exact output file path
- `--format` (required) — Output format (QuickTime, MP4, MXF OP1A, Wave, AIFF)
- `--codec` (required) — Output codec
- `--width` (optional)
- `--height` (optional)
- `--fps` (optional)
- `--video/--no-video` (optional, default: `true`)
- `--audio/--no-audio` (optional, default: `true`)

## Boundaries and gotchas

- The output must be an exact filename with an extension and must not already exist.
- Width and height must be supplied together, and at least one stream must remain enabled.
- Real DaVinci Resolve verification is required before making environment-specific format or codec support claims.

## Examples

- `cutagent render export-file --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
