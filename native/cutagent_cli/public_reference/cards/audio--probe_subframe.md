# `audio probe-subframe`

Syntax: `cutagent audio probe-subframe [--force] [--render]`

## Search terms

- can DaVinci Resolve place audio between frames
- test subframe audio support
- verify sample accurate timeline append
- does Resolve quantize audio to frames
- render proof for subframe sync
- cached subframe verdict

## What it does

Probe whether the connected DaVinci Resolve honors fractional (sub-frame) audio placement.

## Do not use when

Do not use this to measure the offset between recordings; use `audio waveform-offset`.

## Preflight and readback

Run in a disposable project after recording the current timeline and listing project timelines/media. Dry-run first. Afterward verify the prior timeline is current and the scratch timeline/media are absent. Before applying a fractional waveform offset, require a verdict appropriate to the desired proof level.

## Public arguments and options

- `--force` (optional, default: `false`) — Re-probe even when a cached verdict exists
- `--render/--no-render` (optional, default: `true`) — Verify rendered audio position, not only clip metadata

## Boundaries and gotchas

- `--force` bypasses cache.

## Examples

- `cutagent audio probe-subframe --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
