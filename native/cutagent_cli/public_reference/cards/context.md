# `context`

Syntax: `cutagent context`

## Search terms

- where am I in DaVinci Resolve
- current editing context
- current playhead position
- current video item
- timeline track counts
- timeline in and out marks
- current page project timeline
- orient before editing

## What it does

Check the current DaVinci Resolve editing context.

## Do not use when

Do not use `context` merely to ask whether DaVinci Resolve is installed or connected when no project/timeline may be open; use `status`, which tolerates Project Manager and disconnected states. Do not use its compact track string as a clip inventory; use `clip list`, `timeline items`, or a track-specific readback. Do not use it to inspect project resolution, timeline start frame, or every project setting; use `info`, `project info`, or `timeline info`.

## Preflight and readback

Run after `status` confirms an open project and immediately before a timeline edit whose target depends on page, playhead, marks, or current item. After a playhead, mark, timeline-switch, or track-structure command, rerun `context` to verify the corresponding field; after a property mutation, use the property's dedicated readback instead.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- In/out marks are returned only when both endpoints exist for a media kind.
- They are timeline-domain values; do not reinterpret them as source-media timecodes.
- Audio-only context and GUI selection are not represented.

## Examples

- `cutagent context --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
