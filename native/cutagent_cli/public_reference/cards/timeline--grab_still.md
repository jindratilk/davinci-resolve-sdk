# `timeline grab-still`

Syntax: `cutagent timeline grab-still [--output VALUE]`

## Search terms

- grab current timeline still
- Gallery still current frame
- export current playhead image
- current frame still capture
- DaVinci Resolve timeline still
- optional output still path

## What it does

Grab still from current frame.

## Do not use when

Do not use this command when the playhead must first move to a specific frame or later be restored.
Do not rely on `--dry-run` for safety.
This route does not check file existence, size, format, dimensions, or rendered pixels.

## Preflight and readback

Before execution, inspect the active timeline and exact playhead frame.
After execution, verify that the intended Gallery still appeared or that the output file exists and opens correctly.

## Public arguments and options

- `--output/-o` (optional) — Optional output image path

## Boundaries and gotchas

- Exact help is `cutagent timeline grab-still [--output PATH]`.
- `--output`/`-o` is optional.
- The command has no command-level dry-run branch.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline grab-still --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
