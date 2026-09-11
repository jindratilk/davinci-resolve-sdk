# `clip offset`

Syntax: `cutagent clip offset [NAME]`

## Search terms

- inspect left and right source offset
- how much media remains beyond edit
- check available frames for trimming
- get timeline item offsets
- diagnose clip handle length
- see head and tail trim margin

## What it does

Check left and right offset of a clip.

## Do not use when

Use `clip source-range` when the requested facts are source in/out and duration, and `clip info`/`clip list` for record-domain start/end. Use trim, slip, slide, or source-replace commands to change an edit; `clip offset` has no setter. Do not use these two values as record timecodes or as proof that media is online/decodable.

## Preflight and readback

First identify the exact occurrence and separately capture its record range and source range. For an edit decision, confirm the relevant side has sufficient handles and still verify the proposed trim against source bounds and linked audio/video behavior.

## Public arguments and options

- `NAME` (optional) — Clip name (or current if omitted)

## Boundaries and gotchas

- Left/right availability can differ from the source-range fields and depends on how DaVinci Resolve represents the timeline item, speed changes, stills, generators, nested timelines, or multicam content.
- It fails only when neither method exists or both values are null.
- Duplicate names are first-match only and there is no track/frame selector.
- This command does not verify that a subsequent trim will preserve linked-item sync or avoid a transition conflict.

## Examples

- `cutagent clip offset --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
