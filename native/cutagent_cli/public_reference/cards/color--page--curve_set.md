# `color page curve-set`

Syntax: `cutagent color page curve-set [CLIP_NAME] [--all VALUE] [--y VALUE] [--red VALUE] [--green VALUE] [--blue VALUE] [--require-render-proof]`

## Search terms

- set custom curve endpoint
- adjust curve high point
- move Y curve endpoint
- set RGB curve endpoints
- custom curves Edit values
- change red green blue endpoint
- linked curve endpoint adjustment

## What it does

Set Color Page Custom Curves endpoint values using project and rendered-frame proof.

## Do not use when

Use `color page curve-points-set` when shaping a curve with normalized control points, or `curve-spline-set` for the single-channel convenience wrapper. Use primary/wheel controls for lift/gamma/gain rather than trying to approximate them with endpoint metadata. Do not use `curve-set` to move the black/low endpoint, add a midpoint, choose Bezier handles, or target a later Color node—none of those are exposed.

## Preflight and readback

Before running, read/export the active grade and decide whether linked `--all` or channel-specific high points are intended. Record current endpoint values and a representative proof frame.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--all` (optional) — Set Custom Curves Edit Y/R/G/B endpoint value (0-100)
- `--y` (optional) — Set Custom Curves Edit Y endpoint value (0-100)
- `--red` (optional) — Set Custom Curves Edit Red endpoint value (0-100)
- `--green` (optional) — Set Custom Curves Edit Green endpoint value (0-100)
- `--blue` (optional) — Set Custom Curves Edit Blue endpoint value (0-100)
- `--require-render-proof/--setup-only` (optional, default: `true`) — Export before/after Color Page frames and fail unless rendered pixels change

## Boundaries and gotchas

- Do not pass normalized 0..1 values unless that very small UI value is intended.
- Per-channel options win over `--all` only for the channels present; this allows mixed requests but can surprise an agent expecting `--all` to be exclusive.
- `--setup-only` suppresses this check and is not visual proof.

## Examples

- `cutagent color page curve-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
