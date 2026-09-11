# `clip audio-pitch`

Syntax: `cutagent clip audio-pitch [NAME] [--semitones VALUE] [--cents VALUE] [--at VALUE]`

## Search terms

- pitch shift one audio clip
- raise voice by an octave
- lower clip pitch
- transpose timeline audio
- change pitch without changing clip duration
- detune clip by cents
- semitone shift linked audio occurrence
- make this sound higher or lower

## What it does

Set linked audio pitch.

## Do not use when

Use `clip speed`/`clip reverse`/retime commands when playback duration or speed should change. Use Fairlight pitch processing when automation, formant control, or a track-wide effect is required. Use source channel mapping commands for wrong channel assignments. Do not use this as sample-rate correction or audio synchronization; it intentionally changes perceived pitch while preserving timeline duration.

## Preflight and readback

Resolve the exact occurrence with name plus record-domain `--at`; record source duration, sample rate, existing effects, and a baseline render. Use a disposable/checkpointed Disk project. After reopen, confirm duration/start/end are unchanged, render the same span, measure or listen to fundamental frequency, and inspect whether other clip effects survived. For speech/music, listen for artifacts and formant changes rather than relying only on numeric pitch.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--semitones` (optional, default: `12`) — Semitone shift
- `--cents` (optional, default: `0`) — Cent offset
- `--at` (optional) — Record-domain position for deterministic clip selection

## Boundaries and gotchas

- Video-only targets and ambiguous repeated names fail selection.
- `--at` is record-domain; timeline start offset is applied.
- Duplicate `--semitones` or duplicate `--cents` options are explicitly rejected.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip audio-pitch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
