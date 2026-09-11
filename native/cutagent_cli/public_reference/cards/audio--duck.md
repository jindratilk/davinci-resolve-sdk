# `audio duck`

Syntax: `cutagent audio duck INPUT_MEDIA --speech-track VALUE --music-track VALUE [--threshold-db VALUE] [--ratio VALUE] [--attack-ms VALUE] [--release-ms VALUE] [--output VALUE] [--replace-media VALUE]`

## Search terms

- duck music under speech
- lower background music when talking
- quiet music beneath dialogue
- sidechain music to voice
- compress music from dialogue track
- make narration audible over music
- automatic dialogue ducking
- mix speech and music to one file
- relink ducked media in Media Pool

## What it does

Apply dialogue ducking.

## Do not use when

Do not use this for non-destructive timeline/track ducking that should remain adjustable in Fairlight; use a Fairlight dynamics/sidechain or automation workflow. Do not use it to lower every music clip on a timeline based on separate dialogue clips unless those signals have first been rendered/muxed as distinct streams in one file. Do not confuse stream numbers with DaVinci Resolve track indices or container-wide ffprobe indices. Use `clip audio-gain` for a fixed gain on one timeline item and Fairlight track/bus gain for mixer-level changes. Do not use `--replace-media` when only one timeline occurrence should change, because relinking a Media Pool item can affect all uses of that source.

## Preflight and readback

Run `audio info` on the input and map the ordered audio-stream list to speech/music; verify the two roles by listening, not by guessing. After writing, run `audio info` and waveform/listening or loudness comparison on the output. If relinking, first identify the unique Media Pool item and every timeline use, then verify its source path and all affected timeline instances afterward.

## Public arguments and options

- `INPUT_MEDIA` (required) — Input media file
- `--speech-track` (required) — Speech/dialogue audio track index (1-based)
- `--music-track` (required) — Music bed audio track index (1-based)
- `--threshold-db` (optional, default: `-20.0`) — Sidechain threshold in dB
- `--ratio` (optional, default: `8.0`) — Compression ratio
- `--attack-ms` (optional, default: `20.0`) — Attack time in milliseconds
- `--release-ms` (optional, default: `300.0`) — Release time in milliseconds
- `--output/-o` (optional) — Output media path
- `--replace-media` (optional) — Relink Media Pool clip name to ducked output

## Boundaries and gotchas

- Both requested indexes are validated against audio stream count before dry-run.
- The command does not validate that they are different; choosing the same stream uses it as both program and sidechain and then mixes it back.
- Ratio must be 1-20; attack/release must be non-negative; all numeric parameters must be finite.
- Threshold itself has no explicit CLI range beyond finiteness.
- Relink happens only after file generation.

## Examples

- `cutagent audio duck --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
