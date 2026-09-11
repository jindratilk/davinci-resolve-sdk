# `media stereo-create`

Syntax: `cutagent media stereo-create LEFT RIGHT`

## Search terms

- create stereoscopic Media Pool clip
- pair left and right eye footage
- combine stereo camera clips
- make 3D stereo source
- assign left eye right eye media
- merge two video clips into Stereo item
- create DaVinci Resolve stereo pair
- pair matching left right renders

## What it does

Create a stereo clip from left and right media pool items.

## Do not use when

Use ordinary timeline stacking, multicam, split-screen, or compound-clip commands when both sources must remain independently editable in the Media Pool/timeline. Use `media duplicate`/import first if a separate right-eye Media Pool object must survive the pairing.

## Preflight and readback

Exact-search both sources and verify matching duration, frame rate, resolution, timecode, and intended eye order. Preserve metadata/markers and checkpoint the project because the right Media Pool object can disappear. Inspect stereoscopic playback/settings in DaVinci Resolve before reporting usable 3D media.

## Public arguments and options

- `LEFT` (required) — Left-eye Media Pool clip
- `RIGHT` (required) — Right-eye Media Pool clip

## Examples

- `cutagent media stereo-create --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
