# `color page qualifier-sample`

Syntax: `cutagent color page qualifier-sample --x VALUE --y VALUE [--radius VALUE] [--at VALUE] [--output VALUE]`

## Search terms

- sample pixel for qualifier
- pick color from rendered frame
- measure hue saturation luma at point
- get HSL seed from image patch
- inspect RGB under coordinates
- average color around point
- choose HSL key range from footage
- export Color page frame and analyze patch

## What it does

Sample Color Page viewer color values.

## Do not use when

Use `qualifier-gui-hsl-set` or `qualifier-matte-refine` to actually create/change a key; this command only measures rendered pixels. Use `scope-read` for whole-frame distributions rather than one local patch, and `white-balance-picker` when the sampled neutral patch should immediately drive an RGB gain correction. Do not use this as a source-media sampler when grades, effects or output transforms must be excluded: it measures the rendered Color-page frame after the active processing. Do not expect it to target a clip by name; use `--at` or position the playhead explicitly.

## Preflight and readback

Before sampling, put the intended timeline and frame under the playhead, confirm whether active grades/output transforms should be included, choose a small patch fully inside a representative flat region, and use a unique output file if an earlier frame must be preserved. With `--at`, record the intended timecode and ensure it resolves to the correct clip. Afterward, inspect export metadata and the image itself, verify center pixel/bounds/pixel count, and compare HSV/HSL/vectorscope values with the visible patch.

## Public arguments and options

- `--x` (required) — Normalized sample X coordinate across the Color Page frame (0..1)
- `--y` (required) — Normalized sample Y coordinate down the Color Page frame (0..1)
- `--radius` (optional, default: `3`) — Pixel radius around the sample point (0..200)
- `--at` (optional) — Optional timeline position to sample before restoring the playhead
- `--output/-o` (optional, default: `"color_qualifier_sample.png"`) — Exported frame path used for sample analysis

## Boundaries and gotchas

- `--at` changes the playhead before export and restoration is best-effort.
- ffprobe and ffmpeg are required after DaVinci Resolve reports export success.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page qualifier-sample --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
