# `fairlight eq set`

Syntax: `cutagent fairlight eq set [BANDS]`

## Search terms

- set multi-band clip EQ
- high-pass dialogue rumble
- low-pass audio clip
- boost voice presence frequency
- cut harsh frequency with bell EQ
- notch hum on clip
- build Fairlight equalizer from scratch
- replace clip EQ bands
- set EQ frequency gain and Q

## What it does

Set multi-band EQ from scratch.

## Do not use when

Do not use this command when the intended clip must be selected by name, timeline occurrence, track, or time. Do not use clip EQ when the processing must apply to every clip on a Fairlight track or bus; use an actual track/bus processing workflow in DaVinci Resolve instead. Use `clip audio-gain` for broadband level changes, dynamics commands for compression/gating/limiting, and Voice Isolation for supported speech/background separation rather than attempting those jobs with EQ.

## Preflight and readback

Validate the exact spec with global `--dry-run`; this catches shape/band/grammar errors without connecting or mutating.

## Public arguments and options

- `BANDS` (optional) — Band spec: 'B1:high-pass@80 B2:bell@1k+6dB/Q2 B6:low-pass@12k'

## Boundaries and gotchas

- `fairlight eq read` generally cannot decode this command's output.
- Avoid duplicate B labels because their DaVinci Resolve interpretation is not established.
- Frequency and Q must be positive, but the CLI does not enforce a documented audible maximum or a safe gain range.
- It does not decode the curve, inspect the GUI, render audio, or prove that DaVinci Resolve applied the requested filter audibly.

## Examples

- `cutagent fairlight eq set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
