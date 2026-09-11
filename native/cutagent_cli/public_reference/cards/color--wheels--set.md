# `color wheels set`

Syntax: `cutagent color wheels set [CLIP_NAME] [--node VALUE] [--lift VALUE] [--gamma VALUE] [--gain VALUE] [--sat VALUE] [--mode VALUE] [--lut-output VALUE]`

## Search terms

- set color wheels
- adjust lift gamma gain
- change shadows midtones highlights color
- primary color correction
- tint darks mids highlights
- set clip saturation with wheels
- apply CDL equivalent wheels
- emulate DaVinci Resolve primaries
- grade clip with RGB lift gamma gain
- create wheel curves LUT
- warm shadows cool highlights
- apply wheel look to color node

## What it does

Runs the public `color wheels set` CutAgent command.

## Do not use when

Use dedicated primary-control commands for contrast, pivot, temperature, tint, offset/master controls or other controls this command does not expose.
Do not use `--mode lut` for saturation-only work: `--sat` is omitted from the generated RGB curves and is not applied by any CDL route in LUT-only mode. Do not use this command for selective hue/luma work, qualifiers, windows or tracking; use the corresponding curve/qualifier/window/tracker commands. Use a duplicated color version first when the current grade must remain recoverable.

## Preflight and readback

Specify all lift/gamma/gain groups intentionally: omitted groups are filled with neutral defaults and still participate in the resulting write/LUT. Decide whether the request truly means `cdl`, `lut`, or cumulative `both`.
Afterward, require the intended route fields and verify the exact active project/timeline/clip/version after any reopen. Inspect pixel/color changes, not just file existence. Save explicitly after LUT-only mode if the assignment should persist, and restore the prior version rather than trying to reverse the wheel math in place.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name (current clip when omitted)
- `--node` (optional, default: `1`) — Node index
- `--lift` (optional) — Lift triplet 'R G B'
- `--gamma` (optional) — Gamma triplet 'R G B'
- `--gain` (optional) — Gain triplet 'R G B'
- `--sat` (optional) — Saturation multiplier
- `--mode` (optional, default: `"cdl"`) — Compatibility mode: cdl|lut|both
- `--lut-output` (optional) — Output path for generated LUT

## Boundaries and gotchas

- Do not bypass this guard via an external server that cannot safely survive close/reopen.
- LUT-only mode ignores saturation.
- Numeric triplets must contain exactly three parseable values, separated by spaces and/or commas, but there is no explicit finite/range validation for wheel or saturation values.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color wheels set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
