# `timeline still grab-all`

Syntax: `cutagent timeline still grab-all [--source VALUE]`

## Search terms

- grab stills for all timeline clips
- Gallery still per clip
- grab first frame stills
- grab middle frame stills
- batch Gallery still capture
- current timeline clip stills

## What it does

Grab stills for all clips on the current timeline.

## Do not use when

Do not use this command to export image files, create a contact sheet/preview, grab only selected clips, choose exact frames, or capture the timeline's first/middle frame globally.
Do not run it on a large timeline without reviewing Gallery/storage impact and a cleanup plan. The command provides no album selector, deduplication, naming, undo, or delete-on-failure.

## Preflight and readback

Before execution, save/checkpoint the project; activate the exact timeline; inspect clip count/types, Gallery album/state, available storage, and whether first or middle frames are useful.
Verify one still per intended clip, frame choice, grade/image correctness, duplicates, Gallery album placement, and project persistence; remove unwanted stills manually.

## Public arguments and options

- `--source` (optional, default: `"first"`) — Still source: first or middle

## Boundaries and gotchas

- Dry-run does not normalize or validate source.
- The command targets only the current active timeline.
- The result does not include clip names, tracks, record frames, still labels, Gallery album, still ids, thumbnails, file paths, or per-clip failures.
- It does not save/export the project or Gallery.
- It does not detect duplicated pre-existing stills.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent timeline still grab-all --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
