# `clip audio-pan`

Syntax: `cutagent clip audio-pan [NAME] --value VALUE [--at VALUE]`

## Search terms

- pan one clip left or right
- move clip audio in stereo field
- make this timeline clip come from right speaker
- set linked audio pan
- rebalance one clip between channels
- clip-level stereo placement
- pan dialogue occurrence
- adjust audio item pan value

## What it does

Set linked audio pan.

## Do not use when

Use Fairlight track pan when all material on a track needs the same placement, or Fairlight automation when pan must change over time. Use source audio mapping/stereo-value commands when channel interpretation or left/right source assignment is wrong. Use `clip audio-gain` for equal level change in both channels. Do not use this to create a stereo pair from two mono sources.

## Preflight and readback

Identify the exact audio occurrence with `clip linked list` and `--at`, inspect whether the source is mono/stereo and capture a baseline stereo render. After reopening, render the same span and compare channel RMS/peaks, then audition on stereo headphones/speakers. Confirm the intended project/timeline returned and that prior gain/EQ/fades were not unintentionally removed.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--value` (required) — Pan value
- `--at` (optional) — Record-domain position for deterministic clip selection

## Boundaries and gotchas

- It does not prove channel output.
- Post-reopen stereo render or Fairlight meter proof is required.
- `--at` is timeline/record-domain time, not source time.
- Omit the name only when current-item resolution is deterministic; otherwise repeated names or linked groups can be ambiguous.
- Duplicate `--value` options are also explicitly rejected.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip audio-pan --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
