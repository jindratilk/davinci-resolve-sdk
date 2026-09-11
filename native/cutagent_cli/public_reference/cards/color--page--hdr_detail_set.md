# `color page hdr-detail-set`

Syntax: `cutagent color page hdr-detail-set [CLIP_NAME] --zone VALUE [--x VALUE] [--y VALUE] [--sat VALUE] [--range VALUE] [--falloff VALUE]`

## Search terms

- HDR highlight detail
- HDR specular controls
- tune highlight wheel range
- adjust specular falloff
- HDR palette highlight saturation
- change highlight zone x y
- set HDR detail range
- shape specular zone

## What it does

Runs the public `color page hdr-detail-set` CutAgent command.

## Do not use when

Use `hdr-global-set` for overall HDR exposure/saturation and `hdr-zone-set` for Dark/Shadow/Light X/Y/Z or simple Highlight/Specular X/Y/Sat. Use this detail command specifically when Highlight/Specular range/falloff payloads are needed. Do not use it for a `light` zone—the similarly named Light wheel belongs to `hdr-zone-set` and has X/Y/Z semantics.

## Preflight and readback

Record current Highlight/Specular vector, saturation, range and falloff.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--zone` (required) — HDR detail zone: highlight, specular
- `--x` (optional) — HDR detail X vector value
- `--y` (optional) — HDR detail Y vector value
- `--sat` (optional) — HDR detail saturation control
- `--range` (optional) — HDR detail range boundary
- `--falloff` (optional) — HDR detail falloff control

## Boundaries and gotchas

- Only `highlight` and `specular` are accepted.
- All X/Y/Sat/Range/Falloff values use one generic finite -4..4 validator.
- The execution route changes when range/falloff is present.
- X/Y/Sat alone uses the main HDR palette and can seed HDR companion state; adding range/falloff switches to a separate pre-existing HDR-detail container and can fail if that exact container is absent.
- The range route supplies Sat=1.0 when the target zone has no saturation entry.
- A request only for range can therefore seed saturation metadata as well.
- Default range metadata differs by zone: Highlight uses range 1.5/anchor 0.2/falloff about 0.71215, while Specular uses 4.0/0.1/0.1, unless existing values are present.

## Examples

- `cutagent color page hdr-detail-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
