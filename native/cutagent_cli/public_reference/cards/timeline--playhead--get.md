# `timeline playhead get`

Syntax: `cutagent timeline playhead get`

## Search terms

- current playhead timecode
- where is timeline cursor
- get playhead position
- current timeline time in seconds
- record-frame cursor location
- position before edit
- verify playhead move

## What it does

Read current playhead position.

## Do not use when

Do not use it to identify the clip under the cursor; use `timeline current-item` or `timeline item-at` and respect their video/item targeting rules. Do not use it for source-media position or source frames. Use `timeline playhead set` when navigation is intended.

## Preflight and readback

Capture it before any command that temporarily moves the playhead and should restore it. After `timeline playhead set`, frame export, thumbnail, or GUI navigation, rerun and compare exact timecode/frame.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It does not state whether the playhead lies over content, a gap, or beyond the last item.
- It requires an active timeline; Project Manager/project-only state is an error.

## Examples

- `cutagent timeline playhead get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
