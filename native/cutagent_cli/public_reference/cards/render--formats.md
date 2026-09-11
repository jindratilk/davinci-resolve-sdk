# `render formats`

Syntax: `cutagent render formats [--media VALUE]`

## Search terms

- list render formats
- DaVinci Resolve output containers
- render format extensions
- QuickTime MP4 Wave formats
- Deliver format inventory
- query available render formats

## What it does

List available video and audio render formats.

## Do not use when

Do not treat this as a static cross-machine support matrix. Availability may vary by DaVinci Resolve version/edition, host platform, hardware, and installed codecs.
Do not infer codec, resolution, alpha, audio, profile, or export success from format presence alone.

## Preflight and readback

Before querying, record the connected DaVinci Resolve version/edition, host platform, active project, and relevant encoder environment.
After the query, preserve each `format`/`description` pair. Run `render codecs FORMAT` and `render resolutions` for the intended route, then use a settings dry-run and a short real render to validate the complete combination.

## Public arguments and options

- `--media` (optional, default: `"video"`) — Format inventory: video or audio.

## Boundaries and gotchas

- The command is read-only but requires a current project.
- No command-specific dry-run branch exists.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render formats --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
