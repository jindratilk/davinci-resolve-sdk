# `timeline duration`

Syntax: `cutagent timeline duration`

## Search terms

- how long is timeline
- timeline total frames
- sequence start and end
- check empty timeline
- current timeline duration
- playhead and track count summary
- timeline length readback
- duration before render or edit

## What it does

Check the current timeline duration.

## Do not use when

Do not use this to measure one clip (`clip info`/timeline item readback), source-media duration (`media info`), or a marked render range. Do not infer that the Media Pool/project is empty from an empty timeline. Do not use it as a full timeline inventory; `timeline summarize`, items, and track commands expose contents. Do not use it to set duration; `timeline items set-duration` changes an item, while timeline length normally follows its contents.

## Preflight and readback

Run after confirming/switching to the intended timeline and before range-based render/export or duration-sensitive edits. After appending, trimming, deleting, or retiming edge items, rerun and compare start/end/total frames. Use item-level readbacks to explain which edit changed the boundary and GUI/render proof when visible duration matters.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Track counts are contextual convenience and do not identify enabled/locked tracks or contained items.
- It requires an active timeline and cannot return a project-only result.

## Examples

- `cutagent timeline duration --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
