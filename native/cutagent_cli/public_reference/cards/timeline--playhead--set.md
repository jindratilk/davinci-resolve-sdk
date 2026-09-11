# `timeline playhead set`

Syntax: `cutagent timeline playhead set POSITION`

## Search terms

- move playhead
- go to timeline timecode
- jump to frame
- seek timeline cursor
- move to 90 seconds
- navigate to record position
- set current timeline frame
- jump one second from timeline start

## What it does

Set playhead position.

## Do not use when

Do not use this to change the timeline's start timecode (`timeline set-start-tc`), set mark-in/out (`timeline mark set`), seek within source media, or reposition a clip. Do not assume a bare timecode is relative without comparing it to timeline start. Do not use a frame value from source domain; inputs are record/timeline domain.

## Preflight and readback

Choose an unambiguous absolute timecode or suffix-based relative seconds/frames, execute, and require final frame within the command's one-frame tolerance. Rerun `playhead get` or the command-specific item/frame readback. Restore the captured pre-position after temporary inspection/export workflows.

## Public arguments and options

- `POSITION` (required) — Position: timecode (00:01:30:00), seconds (90.5s), or frames (2250f)

## Boundaries and gotchas

- Cursor success does not imply an item exists there.

## Examples

- `cutagent timeline playhead set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
