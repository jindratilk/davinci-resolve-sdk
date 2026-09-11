# `color still grab-all`

Syntax: `cutagent color still grab-all [--source VALUE]`

## Search terms

- grab still for every timeline clip
- create Gallery stills from all shots
- capture midpoint of each clip
- capture first frame of every clip
- batch grab Color page stills
- make reference stills for timeline
- populate Gallery from all clips
- create one grade still per shot
- grab all timeline thumbnails to Gallery
- capture every clip's grade state
- batch stills for color matching
- build Gallery contact set from timeline

## What it does

Grab stills for all clips on the current timeline.

## Do not use when

Use `color gallery still grab` for one still at the current frame/target rather than every clip. Use `timeline grab-still` or `timeline frame-export` when a specific timeline position or image file is required. Use Gallery album create/switch first when stills must land in a specific named album; this command cannot choose one. Use `color source-grade apply-cdl`/render proof when stills are intended as machine verification—grab-all only creates Gallery assets and does not compare pixels. Do not use it for a curated representative frame other than first/middle, for only selected clips/tracks, or for automatically named/mapped stills.

## Preflight and readback

Before running, record current timeline, page, playhead, selected Gallery album and its exact still list/count. Inspect timeline clip/track count and choose first vs middle based on fades/slates/content. Switch/create the intended ordinary Gallery album explicitly and ensure it is not a PowerGrade album unless that is desired. Save enough mapping information to later associate returned order with timeline items, because command output contains no clip identity.
Afterward, run `color gallery still list` against the intended album and verify count increase, labels/order and visual thumbnails; compare expected eligible clips with actual additions. Check current page, playhead and album selection and restore them manually as needed. Rename/export stills immediately if durable clip mapping matters.

## Public arguments and options

- `--source` (optional, default: `"first"`) — Still source: first or middle

## Boundaries and gotchas

- The command has no `--album`; whatever Gallery album/context DaVinci Resolve considers current receives the new stills.
- The command does not move the playhead itself or save/restore it.
- A partial list is accepted without warning, so post-list is required.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color still grab-all --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
