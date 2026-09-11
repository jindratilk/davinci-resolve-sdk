# `fusion template apply`

Syntax: `cutagent fusion template apply TEMPLATE [--clip VALUE] [--track VALUE] [--record-frame VALUE]`

## Search terms

- apply Fusion template
- import template setting
- template .setting path
- template by name
- deterministic Fusion clip selector
- Fusion template track frame
- replace clip Fusion graph
- template auto-layout
- embedded Fusion template
- studio external Fusion template
- fusion.mutation template
- template graph readback

## What it does

Apply a Fusion template to a clip.

## Do not use when

Do not use this command when a new holder clip is required.
Do not use it to render placeholders or author a template.
Do not use a clip name when duplicates make identity uncertain. Prefer the deterministic `--track` plus `--record-frame` selector.
Do not combine `--clip` with track/frame selection, and do not supply only one half of the track/frame pair.
Do not apply over a valuable composition without exporting its graph and representative frames first.
Export the exact composition and render an in-range frame.

## Preflight and readback

Before execution, confirm the project, timeline, video track, record-domain position, clip boundaries, and existing Fusion composition count. Export the current graph and a representative frame.
Inspect and validate its MediaOut, tool graph, fonts, media dependencies, plugins, expressions, frame range, and layout.
Run global dry-run.
Inspect tool classes, SourceOp edges, text/media values, and layout; render a frame within the clip and visually compare it with the expected output.

## Public arguments and options

- `TEMPLATE` (required) — Template name or .setting path
- `--clip` (optional) — Clip name (or current)
- `--track` (optional) — Video track index for deterministic clip selection
- `--record-frame/--at` (optional) — Record-domain frame/time inside the target clip

## Boundaries and gotchas

- Options are `--clip TEXT`, `--track INTEGER` with minimum 1, and `--record-frame/--at TEXT`.
- Dry-run without `--clip`, `--track`, or `--record-frame` does not connect to DaVinci Resolve or verify the current clip.
- Dry-run with `--clip` resolves that named clip.
- Dry-run with track/frame resolves the item at that record-domain position.
- The command replaces/imports composition content on the target clip; it does not merge graphs or preserve the old comp automatically.
- Successful import sets verification status only to `partial`.

## Stable public error codes

- `API_CALL_FAILED`
- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion template apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
