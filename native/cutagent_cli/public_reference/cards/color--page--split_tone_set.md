# `color page split-tone-set`

Syntax: `cutagent color page split-tone-set [CLIP_NAME] [--strength VALUE] [--shadow-cool VALUE] [--highlight-warm VALUE] [--shadow-lift VALUE] [--highlight-lift VALUE] [--pivot VALUE] [--rolloff VALUE] [--shadow-r VALUE] [--shadow-g VALUE] [--shadow-b VALUE] [--highlight-r VALUE] [--highlight-g VALUE] [--highlight-b VALUE] [--y-mood VALUE] [--key-output-gain VALUE]`

## Search terms

- cool shadows warm highlights
- teal shadows orange highlights
- blue shadows warm highlights
- cinematic split toning
- color the darks and lights differently
- add warm highlights without warming shadows
- add cool shadows without cooling highlights
- tint shadows and highlights with RGB curves

## What it does

Runs the public `color page split-tone-set` CutAgent command.

## Do not use when

Use `color page curve-spline-set` or `color page curve-points-set` when the user supplied arbitrary Y/R/G/B Custom Curve points; this command always synthesizes exactly five tonal samples and exposes no handles. Use `color page primary-set` for uniform lift/gamma/gain, temperature or saturation corrections rather than different shadow/highlight tints. Use `color page hdr-global-set` for zone-aware HDR palette controls, or a qualifier/power-window command when the two regions are spatial or selected by hue rather than divided only by luminance around one pivot.

## Preflight and readback

Before the edit, resolve duplicate clip names, confirm the intended local Disk project/timeline and active Color version, and inspect node 1 with `color page read`; save the existing RGB curves because all three will be replaced. If `--y-mood` is nonzero, also save the Y curve. Dry-run every explicit offset, pivot, rolloff, strength and key gain to catch domain errors, but understand that dry-run does not resolve the clip, grade body or active version.
Require every returned RGB control point—and Y when requested—to match the generated values; if `--gain` was supplied, separately require Key Output readback. Then export the same frame and compare shadows, highlights, clipping and neutral midtones. Recheck the playhead/current-item context after reopen rather than assuming it was preserved.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--strength` (optional, default: `1.0`) — Overall split-tone strength, 0..2
- `--shadow-cool` (optional, default: `0.06`) — Cool shadow color curve amount, -0.5..0.5
- `--highlight-warm` (optional, default: `0.06`) — Warm highlight color curve amount, -0.5..0.5
- `--shadow-lift` (optional, default: `0.0`) — Optional neutral shadow curve lift, -0.5..0.5
- `--highlight-lift` (optional, default: `0.0`) — Optional neutral highlight curve lift, -0.5..0.5
- `--pivot` (optional, default: `0.5`) — Split-tone tonal pivot, 0.05..0.95
- `--rolloff` (optional, default: `1.0`) — Shadow/highlight curve rolloff exponent, 0.25..4
- `--shadow-r` (optional) — Explicit red shadow curve offset, -0.5..0.5
- `--shadow-g` (optional) — Explicit green shadow curve offset, -0.5..0.5
- `--shadow-b` (optional) — Explicit blue shadow curve offset, -0.5..0.5
- `--highlight-r` (optional) — Explicit red highlight curve offset, -0.5..0.5
- `--highlight-g` (optional) — Explicit green highlight curve offset, -0.5..0.5
- `--highlight-b` (optional) — Explicit blue highlight curve offset, -0.5..0.5
- `--y-mood` (optional, default: `0.0`) — Optional neutral Y contrast mood curve amount, -0.5..0.5
- `--key-output-gain/--gain` (optional) — Optional Key Output Gain applied after split tone, 0..1

## Boundaries and gotchas

- It does not merge the generated points with existing curve points.
- `--strength 0` is not a no-op.
- It generates identity RGB points and therefore clears any existing RGB curve shapes on node 1; a nonzero existing Y curve survives only when `--y-mood` remains exactly zero.
- Explicit RGB values are raw shadow/highlight offsets, not absolute output values and not additions to `--shadow-cool`, `--highlight-warm` or the lift terms.
- `--y-mood` is asymmetric by construction: it subtracts the scaled amount in shadows and adds it in highlights.
- Rolloff changes only the two interior side samples because the endpoints have weight 1 and the pivot has weight 0.
- Five samples cannot express independently shaped toe, shoulder, tangents or GUI Bezier handles.
- There is no `--node` option, it cannot create a missing grade body/param section, and it can modify the wrong creative layer if node 1 is not the intended look node.
- `--gain` makes the workflow non-atomic.
- Inspect both nested verification objects instead of trusting only the aggregate flag.
- Duplicate-named timeline items can make the intended grade ambiguous; omitting the name binds behavior to the video item under the current playhead.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page split-tone-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
