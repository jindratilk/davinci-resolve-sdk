# `audio waveform-offset`

Syntax: `cutagent audio waveform-offset --reference VALUE --target VALUE [--fps VALUE] [--windows VALUE] [--window-seconds VALUE] [--prior-offset-seconds VALUE] [--metadata]`

## Search terms

- sync audio by waveform
- measure microphone delay
- find offset between recordings
- align external recorder to camera
- calculate subframe audio offset
- detect audio drift between files
- compare BWF timecode and waveform
- how many frames to move target audio
- refine known sync offset

## What it does

Measure the precise audio offset (sub-frame + drift) of target relative to reference.

## Do not use when

Do not use this to apply synchronization; feed the measured correction into the appropriate timeline/media sync command after reviewing sign and confidence. Do not use it when the recordings have no shared audible content, are mostly periodic tones, or were heavily edited independently. Use metadata-only sync logic when trusted BWF/timecode is the required authority and waveform disagreement should not override it.

## Preflight and readback

Run `audio info` on both files and confirm sample/channel/duration plausibility and shared content. Start without a manual prior unless one is independently known; if metadata supplies a prior, inspect it and any mismatch warning. Review windows used/total, spread, peak quality, drift, and sign before mutation.

## Public arguments and options

- `--reference` (required) — Reference media file (offsets are relative to it)
- `--target` (required) — Target media file to align against the reference
- `--fps` (optional, default: `24.0`) — Timeline frame rate used for frame conversion
- `--windows` (optional, default: `7`) — Refinement window count
- `--window-seconds` (optional, default: `30.0`) — Refinement window length in seconds
- `--prior-offset-seconds` (optional) — Skip coarse search and refine around this offset
- `--metadata/--no-metadata` (optional, default: `true`) — Read BWF/timecode metadata and report a deterministic prior

## Boundaries and gotchas

- `fps` affects frame conversion only; waveform correlation remains time/sample based.
- A supplied `--prior-offset-seconds` skips coarse search and can anchor refinement near the wrong match.
- Window count and length must fit useful shared content.
- Drift is reported separately in ppm/span; a single constant offset cannot fix meaningful clock drift across a long recording.

## Examples

- `cutagent audio waveform-offset --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
