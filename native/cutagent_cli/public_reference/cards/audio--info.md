# `audio info`

Syntax: `cutagent audio info INPUT`

## Search terms

- inspect audio file streams
- audio codec sample rate channels
- count audio tracks in media file
- ffprobe audio metadata
- check file has audio
- audio duration and bitrate
- inspect multistream audio file
- preflight external audio processing

## What it does

Read audio processing settings.

## Do not use when

Do not use `audio info` to inspect a timeline item's clip gain, channel mapping, EQ, pan, Fairlight track state, or audible post-mix result; use `clip audio-*`, `clip source-audio-mapping`, or the relevant `fairlight` readback. Do not use it for waveform alignment; use `audio waveform-offset`. Do not infer speech/music roles from stream order or codec metadata.

## Preflight and readback

Run before `audio duck` to confirm at least two audio streams and map its one-based speech/music options to the ordered ffprobe audio-stream list; run before `audio reverb` to confirm audio exists. After file preprocessing, run it on the output to prove a readable audio stream, codec/rate/channel shape, and duration, then add waveform/listening/loudness verification when the actual signal processing matters.

## Public arguments and options

- `INPUT` (required) — Input media file

## Boundaries and gotchas

- The reported per-stream `index` is ffprobe's container stream index and can be zero-based/non-contiguous across video and audio.
- It is not directly the one-based `--speech-track`/`--music-track` numbering used by `audio duck`.
- It cannot see effects, gain, retiming, or routing applied inside DaVinci Resolve.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent audio info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
