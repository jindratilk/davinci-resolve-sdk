# `workflow plugin validate`

Syntax: `cutagent workflow plugin validate PATH`

## Search terms

- validate workflow plugin
- manifest exists check
- plugin folder validation
- workflow integration check
- manifest.json presence

## What it does

Check a custom add-on.

## Preflight and readback

Before execution, point to the intended plugin root. Afterward, run `workflow plugin info`, validate required fields and entrypoint manually, test code, and perform an actual DaVinci Resolve load smoke.

## Public arguments and options

- `PATH` (required) — Plugin folder path

## Boundaries and gotchas

- It does not open or parse the manifest.
- Dry-run has no special branch and performs the same existence checks.

## Examples

- `cutagent workflow plugin validate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
