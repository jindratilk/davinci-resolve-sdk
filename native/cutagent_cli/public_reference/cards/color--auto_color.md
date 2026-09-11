# `color auto-color`

Syntax: `cutagent color auto-color --input VALUE [CLIP_NAME] [--node VALUE] [--frame VALUE] [--apply]`

## Search terms

- automatically correct exposure and white balance
- analyze clip color cast
- normalize dark footage with CDL
- ffmpeg signalstats auto grade
- calculate CDL from a video frame
- inspect luma chroma levels
- auto white balance video file
- brighten footage automatically

## What it does

Generate auto-color correction.

## Do not use when

Use `color page auto-color-ai` for DaVinci Resolve’s own Color-page AI operation, white-balance picker commands for a known neutral sample, or shot-match commands for matching to a reference shot. Do not analyze an arbitrary proxy/file and apply to a different timeline item unless that mismatch is intentional—the command never proves that `--input` backs the target clip.

## Preflight and readback

First run `--no-apply` on a representative frame and inspect the raw stats and proposed values. Confirm the frame exists and is neither a slate, flash, black frame, nor an outlier. If applying, record the target’s current CDL/grade and use an explicit clip name.

## Public arguments and options

- `--input/-i` (required) — Input video file to analyze
- `CLIP_NAME` (optional) — Clip name to apply CDL to
- `--node` (optional, default: `1`) — Node index to apply CDL
- `--frame` (optional, default: `100`) — Frame number to sample for analysis
- `--apply/--no-apply` (optional, default: `true`) — Apply CDL to clip (or just analyze)

## Boundaries and gotchas

- `--no-apply` remains useful.
- Apply dry-run does not run ffmpeg or calculate values.
- It only resolves the clip and says it would analyze/apply.
- Conversely, `--no-apply` proceeds with real ffmpeg analysis even when global dry-run is enabled.
- Only one source frame is sampled.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color auto-color --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
