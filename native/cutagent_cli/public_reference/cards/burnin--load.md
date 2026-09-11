# `burnin load`

Syntax: `cutagent burnin load NAME`

## Search terms

- apply data burn-in preset to project
- load window burn settings
- activate burn-in overlay preset
- use saved timecode burn-in
- switch project data burn-in layout
- apply slate metadata overlay
- load review watermark preset

## What it does

Load a burn-in preset.

## Do not use when

Use `clip burnin load` when the saved configuration must be applied to one current/named timeline item rather than the project-level state. Rendering burn-ins into deliverables requires a later render command and output verification.

## Preflight and readback

Record current project, active timeline, Data Burn-In Project/Clip mode, enabled fields, positions, and representative viewer/render output. Determine the exact user preset name from DaVinci Resolve rather than assuming the CLI catalog is complete. Keep a known prior preset or project checkpoint if restoration matters.

## Public arguments and options

- `NAME` (required) — Burn-in preset name

## Boundaries and gotchas

- Burn-in configuration affects subsequent monitoring/render behavior; it does not permanently bake pixels until media is rendered.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent burnin load --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
