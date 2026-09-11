# `clip linked list`

Syntax: `cutagent clip linked list [CLIP]`

## Search terms

- list items linked to clip
- find linked audio counterpart
- check whether video and audio are linked
- inspect timeline item links
- get linked clip ranges
- verify A V link state
- see companions of current clip

## What it does

List items linked to a timeline item.

## Do not use when

Use `clip link` or `clip unlink` to mutate relationships, and `clip track-info`/`clip list` to locate counterpart tracks.

## Preflight and readback

Identify the exact occurrence and record track/range. Run the command on both video and expected audio sides when possible.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- No source range or duration is included.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent clip linked list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
