# `fairlight record start`

Syntax: `cutagent fairlight record start [--track VALUE]`

## Search terms

- start Fairlight recording
- begin audio capture
- record voiceover now
- start recording armed track
- press Fairlight record
- capture microphone to timeline
- begin ADR take recording
- start audio take
- record on A1
- roll audio recorder
- punch into recording
- create new Fairlight take

## What it does

Check Fairlight audio recording start availability.

## Do not use when

Before pressing Record, manually arm the intended tracks, patch hardware inputs, choose monitoring, confirm levels/sample rate/storage, place the playhead or set the desired range, and manage count-in/preroll as appropriate.
Use `fairlight record arm` only to receive its separate unsupported arm boundary; it cannot prepare a track.
Use timeline/media commands after a manual recording to verify the resulting clip/take and source file.
Do not use a render/bounce command for microphone acquisition.

## Preflight and readback

For the real manual workflow, verify the active project/timeline, save destination/free space, sample rate, audio device, patch, track format, visible arm and input-monitor states, safe monitoring, playhead/range, and existing material that could be overwritten. Perform a level check before rolling.
When finished, stop manually, confirm the take file and timeline clip exist with the expected start/duration/channels, audition it, save the project, and disarm inputs.

## Public arguments and options

- `--track/-t` (optional) — Optional audio track index expected to be armed

## Boundaries and gotchas

- `--track` is optional.
- A supplied track must be an integer >=1, but it is never checked against the active timeline.
- `--track 999` would still be echoed in the same unsupported response.
- `--dry-run` does not yield a successful recording plan.
- There is no separate option for preroll, punch range, file path, filename, sample rate, bit depth, channel count, input device, patch, or monitoring.
- The command cannot protect against this because it performs no preflight.
- It cannot verify a take file, Media Pool item, timeline clip, record duration, dropped samples, or errors.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight record start --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
