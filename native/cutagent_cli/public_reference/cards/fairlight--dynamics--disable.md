# `fairlight dynamics disable`

Syntax: `cutagent fairlight dynamics disable [--track VALUE]`

## Search terms

- disable Fairlight dynamics
- turn off compressor gate limiter
- bypass track dynamics
- stop audio compression
- disable dialogue compressor
- turn off noise gate
- turn off limiter
- remove dynamics processing
- reset dynamics to off
- make Fairlight dynamics inactive
- disable all dynamics modules

## What it does

Disable Fairlight dynamics.

## Do not use when

Do not use this to disable dynamics on one named/numbered track or one timeline in a multi-timeline project. The command has no target selector and overwrites every sequence model in the project.
Do not use this as a clip-FX bypass, plugin removal, bus dynamics bypass, per-clip compressor, or automation-lane edit. It replaces sequence/config blobs.
Do not use it when tuned thresholds/ratios/timing must be recoverable by simply running `enable`.

## Preflight and readback

Before mutating, verify that the current project is the intended local Disk project; do not rely only on the active timeline name.

## Public arguments and options

- `--track` (optional, default: `1`) — Audio track index (1-based)

## Boundaries and gotchas

- A `status: ok` result does not range-check those values.

## DaVinci Resolve editions

Free was not independently exercised for this card.

## Examples

- `cutagent fairlight dynamics disable --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
