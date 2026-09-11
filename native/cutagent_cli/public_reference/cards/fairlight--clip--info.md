# `fairlight clip info`

Syntax: `cutagent fairlight clip info [CLIP]`

## Search terms

- inspect Fairlight timeline clip
- show audio clip metadata
- get TimelineItem start end duration
- inspect clip offsets
- show clip properties
- audio clip inspector
- find clip under playhead
- check clip source handles
- inspect Fusion comp count on clip
- identify timeline item by source filename

## What it does

Check detailed TimelineItem metadata for a Fairlight timeline clip.

## Do not use when

Use `fairlight clip track-info` when track type/index and stable TimelineItem identity are required; `clip info` does not report track location or item ID.
Use `fairlight clip source-range` when the decision specifically needs source in/out and handle interpretation, and `fairlight channel-map clip` for embedded-channel mapping.
Use `media info` or `fairlight channel-map media` when the target is the source asset rather than one timeline occurrence. TimelineItem offsets and duration are occurrence-specific.
Do not use a shared filename/basename when multiple timeline items reference it. This command does not report ambiguity. Inventory track/start/item IDs first, then use a unique TimelineItem name; this command offers no track+record-frame selector.
Do not assume the Fairlight namespace enforces audio-only selection. An explicitly matching video item, or a current video item in omission mode, takes precedence.

## Preflight and readback

Before reading, determine whether the question concerns a TimelineItem occurrence or its Media Pool source.
Afterward, validate `name`, `start`, `end` and `duration` against a track/range inventory. Treat missing optional keys as unavailable, not zero. Use `track-info`, `source-range`, `channel-map clip`, linked-item or gain/pan readers for the specific state needed by the next operation. No mutation verification is necessary because this command changes nothing.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- It does not describe Media Pool Fusion templates or audio effects.
- It can succeed for a nonexistent or ambiguous selector.

## DaVinci Resolve editions

Property dictionaries and getter support can differ across Studio/Free and versions.

## Examples

- `cutagent fairlight clip info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
