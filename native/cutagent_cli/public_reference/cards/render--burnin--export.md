# `render burnin export`

Syntax: `cutagent render burnin export NAME PATH`

## Search terms

- export render burn-in preset
- save delivery overlay settings
- share data burn-in configuration
- back up timecode window burn
- export review watermark preset
- create portable burn-in preset file
- save render metadata overlay

## What it does

Export a burn-in preset.

## Do not use when

Use `render burnin load` to activate a preset for the current rendering context, `render burnin import` to register a portable file, and render-preset export for codec/container/destination settings.

## Preflight and readback

Confirm the preset is visible in Data Burn-In and in the CLI's parsed catalog, inspect overlay fields, and choose a non-colliding writable destination. After success, check the actual file, then import it in a disposable profile and compare a rendered test frame. A returned name/path is not file verification.

## Public arguments and options

- `NAME` (required) — Burn-in preset name
- `PATH` (required) — Export path

## Boundaries and gotchas

- Unlike load, export does not allow an unlisted exact name to reach DaVinci Resolve.
- Exporting a data burn-in preset does not capture a render preset, timeline, metadata values, or rendered pixels—only overlay configuration.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent render burnin export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
