# `color page scope-read`

Syntax: `cutagent color page scope-read [--at VALUE] [--output VALUE] [--mode VALUE]`

## Search terms

- measure waveform levels
- check exposure IRE
- RGB parade statistics
- compare red green blue channel levels
- detect crushed shadows
- detect clipped highlights
- vectorscope chroma measurement
- measure average hue
- analyze current graded frame
- objective Color page frame metrics
- inspect color cast numerically

## What it does

Read waveform and vectorscope-style metrics from the current Color Page frame.

## Do not use when

Use `color page false-color-read` for exposure-band occupancy, and use a rendered before/after comparison when proving a grade changed pixels. Do not use this output as a spatial waveform trace, RGB parade image, gamut plot, or per-region skin detector: all reported channel/hue numbers are whole-frame aggregates with spatial coordinates discarded.

## Preflight and readback

Record the current playhead when subsequent commands depend on it. Interpret percentile/channel data alongside the saved PNG, because a global average can hide localized clipping or opposing color casts. Delete or archive the exported file intentionally; the command leaves it on disk.

## Public arguments and options

- `--at` (optional) — Optional timeline position to sample before restoring the playhead
- `--output/-o` (optional, default: `"color_scope_read.png"`) — Exported frame path used for scope analysis
- `--mode` (optional, default: `"all"`)

## Boundaries and gotchas

- The “waveform” is a global distribution only.
- The IRE conversion then blindly maps code 16 to 0 IRE and 235 to 100 IRE; full-range exports can legitimately produce negative or above-100 reported values.
- Mode filtering only changes returned JSON.
- `--at` temporarily changes the playhead and restores by original timecode.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page scope-read --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
