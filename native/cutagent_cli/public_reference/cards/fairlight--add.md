# `fairlight add`

Syntax: `cutagent fairlight add [--track-type VALUE] [--index VALUE]`

## Search terms

- add audio track
- create new Fairlight track
- append stereo audio track
- add mono dialogue track
- create 5.1 Fairlight track
- add adaptive audio track
- make another empty audio lane
- add surround audio track
- create empty soundtrack lane

## What it does

Add an audio track.

## Do not use when

Use `fairlight ensure-tracks` when the goal is a minimum count without unconditionally adding another track. Use `fairlight track duplicate` when the new track must copy clips or track processing. Use timeline track management for video or subtitle tracks, and bus/effect commands for routing or processing.
Use append mode when preserving existing numeric indices matters.

## Preflight and readback

Before mutation, list audio tracks with names, subtypes, clip counts, locks, routing and mixer state. Decide the exact channel format and whether insertion or append is intended. Preserve a mapping of old track identities to indices.

## Public arguments and options

- `--track-type` (optional, default: `"mono"`) — Audio format: mono, stereo, lcr, 5.1film, 7.1film, adaptive1..adaptive36
- `--index` (optional) — Optional 1-based insertion index

## Boundaries and gotchas

- Despite the generic name, this command only creates an audio track.
- It does not add a clip, effect, bus or Fairlight page object.
- The generated command-index example using `--track-type video` is invalid.
- It does not delete the wrongly formatted new track.
- A successful subtype/count check does not verify track name, routing, channel patching, bus assignment, mixer values or whether existing index-based automation still addresses the intended track.
- Track locks do not prevent adding another track; they are not preflighted.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
