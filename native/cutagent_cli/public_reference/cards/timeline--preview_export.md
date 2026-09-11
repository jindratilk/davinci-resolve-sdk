# `timeline preview-export`

Syntax: `cutagent timeline preview-export [--frames VALUE] [--start-frame VALUE] [--end-frame VALUE] [--step VALUE] --out-dir VALUE --output VALUE [--fps VALUE] [--contact-sheet VALUE]`

## Search terms

- export sampled timeline preview
- timeline frames to GIF
- contact sheet preview
- ffmpeg sampled preview
- visual timeline proof
- export frame sequence
- short edit preview

## What it does

Export a short timeline preview.

## Do not use when

Do not use this as a real-time audiovisual render, delivery master, or proof of audio/timing continuity. It creates a silent slideshow from sampled stills, not a DaVinci Resolve render job.
Do not point `--out-dir` or `--output` at valuable pre-existing generated paths without reviewing overwrite behavior.
Do not assume success means valid source imagery.

## Preflight and readback

Before execution, save the project; verify active timeline, FPS/start frame, sample positions, Color-page export readiness, output parents, available disk space, ffmpeg availability, output suffix, and absence of path collisions. Use dry-run to inspect resolved paths/frame list, then separately validate `fps > 0`.
Open the video/GIF/contact sheet, confirm frame order/count/content and current playhead/page, and retain partial stills for diagnosis if encoding fails.

## Public arguments and options

- `--frames` (optional) — Comma-separated frame refs; overrides --start-frame/--end-frame
- `--start-frame` (optional, default: `0`) — First timeline-relative frame when --frames is omitted
- `--end-frame` (optional, default: `120`) — Last timeline-relative frame when --frames is omitted
- `--step` (optional, default: `4`) — Frame step when --frames is omitted
- `--out-dir` (required) — Directory for intermediate stills
- `--output/-o` (required) — Preview video/GIF path
- `--fps` (optional, default: `12.0`) — Preview playback FPS
- `--contact-sheet` (optional) — Optional contact sheet image path

## Boundaries and gotchas

- Explicit `--frames` overrides start, end, and step completely.
- `--frames` is split on commas, trims whitespace, drops empty parts, and requires at least one remaining reference.
- Without `--frames`, start defaults to 0, end to 120, and step to 4.
- Step must be greater than zero.
- End must be at least start.
- The end frame is always included, even when the step does not land exactly on it.
- Ref sanitization can map different textual references to the same token only when their indices also match; index normally keeps sequence filenames distinct.
- `--out-dir` is required.
- `--output`/`-o` is required and resolves to an absolute file path.
- Dry-run does not require that parent to exist.
- Unsupported/no suffix can fail only after all stills have been exported.
- `--fps` defaults to 12.
- Positive FPS is validated only inside the encoder after frame export.
- GIF encoding hardcodes an output filter of `fps=12` and width 960, regardless of requested `--fps`.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline preview-export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
