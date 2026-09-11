# `clip marker delete`

Syntax: `cutagent clip marker delete FRAME [--frame-domain VALUE] [--clip VALUE]`

## Search terms

- delete clip marker
- remove source marker
- delete marker by clip offset
- erase annotation from timeline item
- remove clip note at frame
- delete raw source-frame marker
- clear marker that follows clip
- remove one marker from named clip

## What it does

Delete a marker from a clip by frame.

## Do not use when

Do not use auto domain for trimmed media when the frame is ambiguous. If every occurrence or every marker color across the timeline must be removed, first enumerate exact clip/item targets; this command affects only the resolved item and one frame.

## Preflight and readback

Preserve metadata if restoration may be needed. Execute with a uniquely named item, then rerun the list and confirm that exact frame disappeared while sibling markers remain; the command does not perform its own post-delete readback.

## Public arguments and options

- `FRAME` (required) — Marker frame value
- `--frame-domain` (optional, default: `"auto"`) — Frame domain: auto, offset, source, or raw
- `--clip` (optional)

## Examples

- `cutagent clip marker delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
