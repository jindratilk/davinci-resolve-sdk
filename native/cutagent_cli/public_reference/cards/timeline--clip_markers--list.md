# `timeline clip-markers list`

Syntax: `cutagent timeline clip-markers list [--color VALUE] [--track-type VALUE] [--track VALUE] [--visible-only]`

## Search terms

- list clip markers across timeline
- find source markers on edited clips
- scan timeline items for clip notes
- locate clip marker occurrences
- show hidden source markers
- find colored clip annotations
- map source marker to record time
- review markers on audio tracks
- list markers that move with clips

## What it does

List timeline clip markers.

## Do not use when

Use a Media Pool marker command when the source asset must be inspected independently of whether or how often it appears on the timeline.

## Preflight and readback

List tracks and confirm the active timeline. Start with the default visible-only scan for the relevant track type, then use explicit repeated `--track` selectors to narrow expensive timelines. If expected source markers are absent, rerun with `--include-hidden-source-markers` and compare source bounds. After clip-marker mutations, scan the same track/type/filter and require the expected occurrence count and metadata.

## Public arguments and options

- `--color` (optional) — Only include clip markers with this color
- `--track-type` (optional, default: `"video"`) — Track type: video, audio, or all
- `--track` (optional, repeatable) — Track index to scan; repeat for multiple tracks
- `--visible-only/--include-hidden-source-markers` (optional, default: `true`) — Only include markers whose source frame is visible in each timeline item

## Boundaries and gotchas

- The default is `--track-type video`; an audio-only marker is invisible until `--track-type audio` or `all` is requested.
- `--track` may be repeated.
- Each selected index is validated against every scanned type; with `--track-type all`, an index missing from either video or audio causes validation failure rather than being silently skipped.

## Examples

- `cutagent timeline clip-markers list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
