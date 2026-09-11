# `color page hdr-zone-set`

Syntax: `cutagent color page hdr-zone-set [CLIP_NAME] --zone VALUE [--x VALUE] [--y VALUE] [--z VALUE] [--sat VALUE] [--range VALUE] [--falloff VALUE]`

## Search terms

- adjust HDR dark zone
- HDR shadow wheel
- HDR light wheel
- set highlight zone
- tune specular saturation
- change dark shadow light x y z
- HDR palette zone correction

## What it does

Runs the public `color page hdr-zone-set` CutAgent command.

## Do not use when

Use `hdr-global-set` for overall HDR Exposure/Saturation and `hdr-detail-set` when Highlight/Specular Range or Falloff is required. Use conventional wheel/primary commands for Lift/Gamma/Gain rather than assuming Dark/Shadow/Light are aliases.

## Preflight and readback

For first-time Highlight/Specular writes, also inspect seeded HDR companion/curve state.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--zone` (required) — HDR wheel zone: dark, shadow, light, highlight, specular
- `--x` (optional) — HDR zone X vector value
- `--y` (optional) — HDR zone Y vector value
- `--z` (optional) — HDR zone Z vector value for dark/shadow/light
- `--sat` (optional) — HDR zone saturation control for highlight/specular
- `--range` (optional) — HDR zone range boundary for highlight/specular
- `--falloff` (optional) — HDR zone falloff control for highlight/specular

## Boundaries and gotchas

- Axis rules are zone-specific: Dark/Shadow/Light allow X/Y/Z only; Highlight/Specular allow X/Y/Sat and explicitly reject Z.
- At least one allowed value is required.

## Examples

- `cutagent color page hdr-zone-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
