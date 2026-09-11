# `color page shot-match-analyze`

Syntax: `cutagent color page shot-match-analyze --reference-at VALUE [--target-at VALUE] [--reference-output VALUE] [--target-output VALUE] [--anchor-x VALUE] [--anchor-y VALUE] [--radius VALUE] [--strength VALUE]`

## Search terms

- match color between two shots
- compare reference and target exposure
- calculate RGB gain shot match
- balance camera angles
- make target look like reference
- analyze shot-to-shot color difference
- sample the same neutral patch in two shots
- match white balance from reference frame
- compare full-frame RGB averages
- recommend primary gains
- quantify exposure mismatch
- anchor-based shot matching

## What it does

Analyze reference and target Color Page frames for exposure and RGB shot matching.

## Do not use when

Use `color page shot-match-apply` only after reviewing this analysis when the user explicitly wants the recommended gains written; analyze never mutates the grade. Use `color page viewer-before-after` for pixel-difference proof rather than gain recommendations, and use `scope-read` for one-frame exposure/chroma statistics. Use Gallery still/wipe/split-screen workflows when visual composition matching is needed. Do not use global matching for shots with different framing, subjects, backgrounds, graphics or letterboxing—the arithmetic will match frame averages, not corresponding scene illumination. Do not use one shared anchor unless the same material/neutral object occupies that normalized coordinate in both shots; there is no feature tracking or registration.

## Preflight and readback

Use separate existing output directories and preserve the current playhead if downstream work depends on it.

## Public arguments and options

- `--reference-at` (required) — Timeline position for the reference shot/frame
- `--target-at` (optional) — Timeline position for the target shot/frame; current playhead when omitted
- `--reference-output` (optional, default: `"color_shot_match_reference.png"`) — Exported reference frame path
- `--target-output` (optional, default: `"color_shot_match_target.png"`) — Exported target frame path
- `--anchor-x` (optional) — Optional normalized shared anchor X coordinate, 0..1
- `--anchor-y` (optional) — Optional normalized shared anchor Y coordinate, 0..1
- `--radius` (optional, default: `12`) — Anchor sample radius in pixels, 0..200
- `--strength` (optional, default: `1.0`) — Recommendation strength, 0..1

## Boundaries and gotchas

- Anchor mode uses the **same normalized X/Y** in both frames; it does not follow an object.
- Coordinates must be finite 0..1 and radius 0..200.
- Final gains are clamped to 0.5..1.5, so `clamped=true` often means the recommendation cannot fully match the measured ratio.
- `--strength` (finite 0..1) blends the raw gain toward 1 before clamping; strength 0 returns neutral applied recommendations while still reporting raw ratios/deltas.
- This floating-point accumulation error slightly biases full-frame gains; do not interpret extra decimals as sensor precision.
- IRE uses Rec.709 luma coefficients and a fixed video-range 16..235 mapping on the decoded 8-bit RGB.
- Full-range values can be below 0 or above 100 IRE.
- The command does not validate that reference and target output paths are distinct.
- Reusing one path overwrites the reference file with the target after the reference pixels are already held in memory; analysis can still succeed, but only the target image remains for audit.
- When `--target-at` is omitted, target capture explicitly seeks back to the original playhead timecode after reference capture.
- Output parent directories must already exist.
- It does not verify that the shots correspond, the recommendation is aesthetically sound, or applying it will match rendered pixels.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page shot-match-analyze --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
