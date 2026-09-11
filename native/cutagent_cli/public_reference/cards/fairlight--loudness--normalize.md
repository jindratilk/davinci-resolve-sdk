# `fairlight loudness normalize`

Syntax: `cutagent fairlight loudness normalize [--target-lufs VALUE]`

## Search terms

- normalize timeline to target LUFS
- set integrated loudness to -16 LUFS
- broadcast normalize to -23 LUFS
- make podcast loudness compliant
- adjust mix to ATSC loudness target
- normalize Fairlight master loudness
- hit streaming LUFS target
- loudness match whole timeline
- normalize programme audio with true peak
- change timeline gain from loudness analysis
- loudness-normalize dialogue and music mix
- apply BS.1770 loudness correction

## What it does

Runs the public `fairlight loudness normalize` CutAgent command.

## Do not use when

Use `clip audio-normalize` when one linked timeline clip should be peak-normalized to a dBFS target.
Use an explicit clip/track gain command only when a trusted analysis has already supplied the required gain and the intended scope is known. For programme loudness, render the exact audible mix/stem, measure it with a trusted BS.1770 analyzer including true peak, calculate a bounded correction, apply it at the intended clip/track/bus scope, then render and measure again.
Do not switch to `fairlight loudness analyze` expecting a preflight measurement; that public command is likewise unsupported.

## Preflight and readback

For an external workflow, preserve a baseline render and measurement, apply a bounded gain change, then re-render and confirm Integrated LUFS, true peak, duration, channels, silence/clipping, and audible quality.

## Public arguments and options

- `--target-lufs` (optional) — Target integrated LUFS

## Boundaries and gotchas

- `--target-lufs` is optional in the CLI and unvalidated beyond float parsing.
- A target number alone cannot distinguish EBU R128, ATSC A/85, streaming conventions, gating, channel weighting, dialogue intelligence, or a true-peak ceiling.
- It does not preview affected clips, gain, scope, or expected output.
- They are not current Integrated LUFS, required gain, or a normalized-state flag.
- It is a different algorithm and scope; a peak-normalized clip can still miss a LUFS target by many decibels.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight loudness normalize --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
