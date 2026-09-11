# `fairlight io patch`

Syntax: `cutagent fairlight io patch [--track VALUE] [--input VALUE] [--output VALUE]`

## Search terms

- patch microphone to Fairlight track
- route hardware input to A1
- assign audio interface input
- patch track direct to output
- route Fairlight track to speakers
- change Patch Input Output matrix
- set record input
- connect system generator to track
- assign track input channel
- patch control room output
- change Fairlight I/O routing

## What it does

Check Fairlight patch I and O availability.

## Do not use when

Use `fairlight tracks` to identify the intended audio track before a manual operation. Configure input/output patches in DaVinci Resolve's Fairlight Patch Input/Output dialog and verify signal/monitoring there. Use `fairlight channel-map` commands only for source/timeline audio-channel mapping; channel mapping and hardware patching are different layers.

## Preflight and readback

If a human patches manually, verify the actual signal/path in DaVinci Resolve rather than rerunning this command as readback.

## Public arguments and options

- `--track/-t` (optional) — Audio track index
- `--input` (optional) — Hardware/input source name
- `--output` (optional) — Hardware/output destination name

## Boundaries and gotchas

- Supplying no options, input only, output only, both input and output, or a positive nonexistent track all reach the same unsupported branch; no semantic request validation runs.
- It cannot discover different capabilities on Studio versus Free or on newly attached hardware.
- Accessibility permissions or opening the Fairlight page cannot change this command's result.
- `--dry-run` has no successful planning branch here.
- Do not mark routing complete or proceed to recording based on it.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight io patch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
