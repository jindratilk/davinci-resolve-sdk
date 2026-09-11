# `color page hdr-global-set`

Syntax: `cutagent color page hdr-global-set [CLIP_NAME] [--exposure VALUE] [--saturation VALUE] [--require-render-proof]`

## Search terms

- HDR global exposure
- HDR palette global saturation
- brighten whole image with HDR wheel
- global HDR correction
- adjust HDR exposure
- change HDR global sat
- set HDR grade overall

## What it does

Set Color Page HDR Global exposure and saturation using project and rendered-frame proof.

## Do not use when

Use `hdr-zone-set` for Dark/Shadow/Light/Highlight/Specular zone controls, `hdr-detail-set` for Highlight/Specular range/falloff, and primary/wheel commands for conventional SDR lift/gamma/gain or Offset controls.

## Preflight and readback

Before running, read/export the active grade, record both current Global values, and choose a frame with visible tonal/chroma content. Inspect curves after a first-time seed as well as the HDR palette.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--exposure/--exp` (optional) — HDR Global Exposure value
- `--saturation/--sat` (optional) — HDR Global Saturation value
- `--require-render-proof/--setup-only` (optional, default: `true`) — Export before/after Color Page frames and fail unless the rendered image changes.

## Boundaries and gotchas

- At least one value is required.
- Default rendered proof compares only the sampled frame.

## Examples

- `cutagent color page hdr-global-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
