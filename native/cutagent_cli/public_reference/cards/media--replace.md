# `media replace`

Syntax: `cutagent media replace CLIP PATH`

## Search terms

- replace Media Pool clip source
- swap source file under timeline edits
- point existing clip to different media
- replace footage without rebuilding timeline
- change audio source for linked timeline item
- replace missing or revised render
- swap proxy-like source permanently

## What it does

Replace a media pool clip's source media.

## Do not use when

Use timeline replace/overwrite commands when only one timeline occurrence should change; this command affects the shared Media Pool source and therefore all occurrences.

## Preflight and readback

Inventory the existing source path, duration, streams, timecode, metadata/markers/marks, Media Pool ID, and every timeline use.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name
- `PATH` (required) — Replacement media path

## Examples

- `cutagent media replace --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
