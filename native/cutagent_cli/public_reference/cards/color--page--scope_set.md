# `color page scope-set`

Syntax: `cutagent color page scope-set [--mode VALUE] [--y-rgb VALUE] [--colorize] [--skin-tone-indicator] [--zoom VALUE]`

## Search terms

- open Color page scopes
- switch to waveform scope
- show RGB parade
- display vectorscope
- show histogram scopes
- open CIE chromaticity scope
- set waveform to Y or RGB
- show YCbCr parade
- colorize waveform
- vectorscope 2x zoom

## What it does

Set Color Page Scopes panel controls through the interface.

## Do not use when

Use frame export/false-color tools for machine-readable exposure evidence.

## Preflight and readback

Before running, bring the intended DaVinci Resolve window to a stable visible display, close obstructing popovers, confirm the Color page can open, and grant Accessibility plus Screen Recording to the actual process hosting CutAgent CLI. Verify `changed=false` is a legitimate no-op only when the returned values already match.

## Public arguments and options

- `--mode` (optional, default: `"parade"`) — Requested GUI scope mode
- `--y-rgb` (optional, default: `"rgb"`) — Requested Y/RGB scope channel mode
- `--colorize` (optional, default: `false`) — Requested GUI scope colorize toggle
- `--skin-tone-indicator` (optional, default: `false`) — Requested vectorscope skin-tone indicator
- `--zoom` (optional, default: `"1x"`) — Requested GUI scope zoom

## Boundaries and gotchas

- The route is macOS-only and uses real global mouse events.
- Maximizing within that display does not satisfy the hard-coded threshold.
- UI scaling, localized labels, panel resizing, multiple displays, a moved window, or a future DaVinci Resolve layout can direct clicks incorrectly; post-click readback catches many mistakes but cannot undo them.
- Calling only `--mode vectorscope`, for example, actively clears vectorscope Colorize/skin-line and resets zoom to 1x.
- Y/CbCr/RGB settings apply only to Parade/Waveform.
- `--colorize` on Histogram or CIE is not rejected, but those modes execute no setting action and verification expects no setting fields; the requested true value is effectively ignored.
- Proof files use second-resolution timestamps in `artifacts/color-scope-gui/`.
- This affects only the operator's scope display.
- It does not change pixels, grade metadata, render output, clip selection, timeline state, or the numeric output of `scope-read`.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page scope-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
