# `fairlight channel-map clip`

Syntax: `cutagent fairlight channel-map clip [CLIP_ARG] [--clip VALUE]`

## Search terms

- inspect source audio channels on clip
- check mono stereo mapping
- show TimelineItem audio map
- get source channel assignment
- see which embedded channels a timeline item uses
- inspect left right channel map
- check muted source channels
- timeline item audio mapping
- verify clip attributes audio channels

## What it does

Read source audio channel mapping for a timeline item.

## Do not use when

Use `fairlight channel-map media` when the question concerns the Media Pool item's base audio mapping rather than a specific timeline instance. Timeline-item mapping can differ from the source asset after Clip Attributes/channel changes.
Do not use an ambiguous clip/file name when multiple timeline items share it. This command does not detect ambiguity or return track/start identity. Resolve an exact unique timeline-item name first, or use a route with item-ID/track-time selectors.

## Preflight and readback

Before reading, map candidate timeline items with track, start/end, TimelineItem ID, display name, source path and Media Pool item name. Choose a selector unique across both video and audio tracks. If relying on omission, verify the playhead is inside the intended item and whether a current video item will take precedence.
Check embedded channel count, every virtual track key, channel indices, mute and type. Correlate the result with `channel-map media` and an audible/render test when mapping determines content. No post-mutation readback is needed because nothing changes.

## Public arguments and options

- `CLIP_ARG` (optional) — Timeline clip name; current clip when omitted
- `--clip` (optional) — Timeline clip name; current clip when omitted

## Boundaries and gotchas

- It cannot reveal which duplicate won.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fairlight channel-map clip --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
