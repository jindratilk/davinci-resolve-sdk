# `clip marker list`

Syntax: `cutagent clip marker list [NAME]`

## Search terms

- list markers on clip
- inspect clip-attached notes
- show source-frame markers
- find marker offset in clip
- check clip marker metadata
- verify clip marker deletion
- see markers that move with clip

## What it does

List markers on a clip.

## Do not use when

Use `timeline clip-markers list` when the task is to find all clip-marker occurrences across tracks or include Media Pool markers. Use `timeline marker list` for position-fixed timeline markers.

## Preflight and readback

Identify the exact timeline item by name or place the playhead over it, then list before changing marker data. Capture source frame and metadata for any marker you may delete.

## Public arguments and options

- `NAME` (optional)

## Examples

- `cutagent clip marker list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
