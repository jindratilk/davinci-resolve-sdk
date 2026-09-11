# `media sync-audio`

Syntax: `cutagent media sync-audio CLIPS... [--mode VALUE] [--channel VALUE] [--retain-embedded-audio] [--retain-video-metadata]`

## Search terms

- sync external audio to video
- auto sync by waveform
- sync clips by timecode
- attach recorder WAV to camera clip
- replace or retain embedded camera audio
- align dual-system sound
- waveform match production audio
- sync Media Pool clips with audio channel
- keep video metadata during sync

## What it does

Sync selected media pool clips.

## Do not use when

Use `audio waveform-offset` when only measuring alignment without mutating Media Pool mapping. Use timeline nudge/slip commands when the audio/video already exist as timeline items and only timeline placement should move. Do not use timecode mode when sources lack trustworthy matching timecode, or waveform mode on silent/non-overlapping material.

## Preflight and readback

Exact-search every video/audio item and inspect timecode, duration, sample rate/channels, and current `media audio-mapping`. After sync, require `synced: true`, compare the video's audio mapping, linked path, offset, track mapping, and retained embedded channels, then audition sync in DaVinci Resolve. Check existing timeline occurrences separately because the command does not enumerate them.

## Public arguments and options

- `CLIPS` (required, repeatable) — Clip names to pass to DaVinci Resolve audio sync
- `--mode` (optional) — timecode|waveform
- `--channel` (optional) — Waveform sync channel number, -1=automatic, -2=mix
- `--retain-embedded-audio/--no-retain-embedded-audio` (optional)
- `--retain-video-metadata/--no-retain-video-metadata` (optional)

## Boundaries and gotchas

- Mode accepts only `waveform` or `timecode` (case-insensitive).
- This changes per-Media-Pool-item audio relationships and can affect future timeline appends/uses; it does not move the playhead or place clips on a timeline.

## Examples

- `cutagent media sync-audio --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
