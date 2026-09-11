# `clip audio-normalize`

Syntax: `cutagent clip audio-normalize [NAME] [--target-dbfs VALUE] [--at VALUE]`

## Search terms

- normalize one clip peak
- set clip peak to target dBFS
- make dialogue clip peak at minus nine
- analyze and adjust timeline clip gain
- peak normalize linked audio occurrence
- automatically calculate clip gain
- match audio item to peak target
- render-measure-normalize clip audio

## What it does

Normalize linked audio level.

## Do not use when

Use `clip audio-gain` when the desired gain offset is already known. Use `audio duck` for time-varying music reduction. Do not run this on a span overlapped by any other audio timeline item, because its render would not isolate the target and the command deliberately refuses that case.

## Preflight and readback

Resolve the exact item, ensure no audio on any track overlaps its half-open start/end range, inspect existing gain/effects, and use a disposable Disk project. Confirm other effects survived and that DaVinci Resolve reopened the intended project/timeline.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--target-dbfs` (optional, default: `-9.0`)
- `--at` (optional) — Record-domain position for deterministic clip selection

## Boundaries and gotchas

- Always preflight the actual codec catalog; do not equate catalog support with an executable render route.
- If DaVinci Resolve emits QuickTime/LPCM, macOS `afconvert` is required to make analysis WAV.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip audio-normalize --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
