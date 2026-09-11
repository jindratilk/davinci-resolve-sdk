# `color page false-color-read`

Syntax: `cutagent color page false-color-read [--at VALUE] [--output VALUE]`

## Search terms

- false color exposure analysis
- check IRE bands
- find clipped highlights
- detect crushed blacks
- measure properly exposed pixels
- exposure heatmap statistics
- shadow and highlight risk
- analyze frame luma bands
- skin exposure range percent

## What it does

Analyze Color Page exposure as false-color-style IRE and luma bands.

## Do not use when

Use `color page scope-read` when waveform/parade/vectorscope channel statistics are needed, `scope-set` to change the visible Scopes panel, and qualifier/white-balance probes for a localized pixel sample. Do not use this command expecting a false-colored PNG overlay: the saved image is the ordinary graded frame; false-color colors exist only as labels in the returned analysis.

## Preflight and readback

Record current playhead when `--at` is used. Interpret the 40–70 IRE bucket in scene context rather than treating it as automatic skin detection.

## Public arguments and options

- `--at` (optional) — Optional timeline position to sample before restoring the playhead
- `--output/-o` (optional, default: `"color_false_color_read.png"`) — Exported frame path used for false-color exposure analysis

## Boundaries and gotchas

- Full-range, HDR/PQ/HLG, data-level and display-managed output can make these video-level IRE labels misleading.
- `--at` moves the real playhead temporarily.
- Output parent must already exist; the command will not create it.

## Examples

- `cutagent color page false-color-read --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
