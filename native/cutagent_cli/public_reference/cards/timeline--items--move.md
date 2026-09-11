# `timeline items move`

Syntax: `cutagent timeline items move [--timeline VALUE] [--track-index VALUE] --start-frame VALUE --current-end-frame VALUE --name VALUE [--to-start-frame VALUE] [--to-track VALUE] [--allow-overlap] [--include-linked-audio] [--allow-linked-video-only]`

## Search terms

- move video clip on timeline
- reposition timeline item
- move clip to another video track
- change clip record start
- preserve linked audio while moving video
- move linked audio and video together
- non-ripple video clip move

## What it does

Move one exact video item with record-time and video-track changes supported independently.

## Do not use when

Use trim, slip, or duration commands when the record start should remain fixed. Do not use this command for audio-primary moves; use `fairlight clip move` instead. Do not use it for compound multi-video link groups, ambiguous selectors, unsaved/cloud projects, transition-aware reflow, or when a protected/locked source, destination, or linked-audio track is involved.

## Preflight and readback

After mutation, independently inspect the full timeline. Require the video item at the exact destination track/range, every included linked-audio item shifted by the same delta, unchanged duration/source/media evidence, preserved linked topology, and no changes to any non-target item or track.

## Public arguments and options

- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--track-index/--track` (optional, default: `1`) — Current video track index
- `--start-frame` (required) — Current video item start in record-domain frames/time
- `--current-end-frame` (required) — Current video item end for exact selection
- `--name` (required) — Current timeline item name for exact selection
- `--to-start-frame/--to` (optional) — New item start in record-domain frames/time
- `--to-track/--to-track-index` (optional) — Destination video track index
- `--allow-overlap` (optional, default: `false`) — Allow overlap with an existing item on the destination video track
- `--include-linked-audio` (optional, default: `false`) — Move every authoritatively linked audio item by the same record-frame delta
- `--allow-linked-video-only` (optional, default: `false`) — Explicitly allow a record move to leave linked audio at its current position

## Boundaries and gotchas

- `--start-frame`, `--current-end-frame`, and `--name` describe the current exact item.
- `--to-start-frame` is the destination.
- At least one of `--to-start-frame` or `--to-track` is required.
- Destination overlap is rejected unless `--allow-overlap` is explicit.
- Transition rows touching an old or new range remain blockers even with overlap allowed.
- Same-name or same-range guesses are not accepted for this video-primary route.

## Examples

- `cutagent timeline items move --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
