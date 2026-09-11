# `color page wheel-set`

Syntax: `cutagent color page wheel-set [CLIP_NAME] [--node-index VALUE] [--lift-r VALUE] [--lift-g VALUE] [--lift-b VALUE] [--gamma-r VALUE] [--gamma-g VALUE] [--gamma-b VALUE] [--gain-r VALUE] [--gain-g VALUE] [--gain-b VALUE] [--sat VALUE] [--require-render-proof]`

## Search terms

- set Color page lift RGB
- adjust gamma color channels
- change gain RGB values
- tint shadows with lift
- tint midtones with gamma
- tint highlights with gain
- verify wheel change with rendered frame

## What it does

Set color wheel values using project readback (Disk projects only).

## Do not use when

Use `color page primary-set` for contrast, pivot, temperature, tint, hue, luminance mix, highlights/shadows, color boost, midtone detail or Offset RGB; `wheel-set` exposes none of those. Use `color page hdr-zone-set`/`hdr-global-set` for HDR palette zones, and curve commands for tonal response curves. Do not use `wheel-set` to create node topology—run and verify `node-add` first for a requested node above 1.

## Preflight and readback

Before writing, inspect `color page read` for the exact clip, active local version, node count and existing per-node raw values. Record the requested values as absolute replacements, not “increase by” amounts, and reject non-finite or implausible numbers in the agent layer because the command does not. For node >1, prove that node exists and contains the intended correction layer.
If render proof was requested, inspect both PNGs and the target metadata, verify the original playhead was restored, and judge whether the direction/locality matches the request; the built-in threshold proves only any nonzero pixel change.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index
- `--lift-r` (optional) — Lift Red
- `--lift-g` (optional) — Lift Green
- `--lift-b` (optional) — Lift Blue
- `--gamma-r` (optional) — Gamma Red
- `--gamma-g` (optional) — Gamma Green
- `--gamma-b` (optional) — Gamma Blue
- `--gain-r` (optional) — Gain Red
- `--gain-g` (optional) — Gain Green
- `--gain-b` (optional) — Gain Blue
- `--sat` (optional) — Saturation
- `--require-render-proof` (optional, default: `false`) — Export before/after Color Page frames and fail unless the rendered image changes

## Boundaries and gotchas

- No numeric range or finiteness checks exist for any wheel/saturation value.
- It emits the same one-line message even with `--require-render-proof`.
- Supplying only `--gain-r` does not reset Gain G/B, but supplying an assumed “default” can overwrite a deliberate existing value.
- A node above 1 cannot be created from an ungraded clip and needs existing topology; this command is not a substitute for `node-add`.
- It does not verify expected channel direction, affected region, absence of clipping, or artistic correctness.
- Duplicate names can be ambiguous; omission targets the current video item and changes the proof-frame selection semantics as described above.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page wheel-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
