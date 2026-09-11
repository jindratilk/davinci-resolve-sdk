# `fairlight ensure-stereo-tracks`

Syntax: `cutagent fairlight ensure-stereo-tracks --count VALUE [--timeline VALUE] [--db-subtype VALUE] [--patch-db-subtype] [--allow-existing]`

## Search terms

- ensure stereo audio tracks
- make all Fairlight tracks stereo
- add missing stereo lanes
- convert mono tracks to stereo
- prepare podcast stereo track layout
- guarantee total audio track count
- fix audio track subtype zero
- normalize timeline tracks to stereo

## What it does

Ensure enough stereo audio tracks.

## Do not use when

Use `fairlight ensure-tracks --track-type stereo` to count existing stereo lanes and append only the deficit. Use `fairlight add --track-type stereo` for one exact lane, and `fairlight track-format set` for an intentional individual-track conversion.

## Preflight and readback

List all tracks, formats, clip counts, and channel expectations before running. Checkpoint a disposable/test project because the default path rewrites every audio track subtype and closes/reopens. Afterward, run `fairlight tracks`, verify total count and every intended format, inspect clips on formerly mono/surround lanes for channel interpretation, and confirm the correct project/timeline reopened.

## Public arguments and options

- `--count` (required) — Minimum number of audio tracks to ensure
- `--timeline` (optional) — Optional target timeline name
- `--db-subtype` (optional, default: `0`)
- `--patch-db-subtype/--no-patch-db-subtype` (optional, default: `true`)
- `--allow-existing/--no-allow-existing` (optional, default: `true`) — If the target already has at least --count audio tracks, do not add more

## Boundaries and gotchas

- `--count` is total audio tracks, not matching stereo tracks.
- It does not create `count` additional tracks.
- Newly added tracks must persist to Disk within the short wait before patching.

## Examples

- `cutagent fairlight ensure-stereo-tracks --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
