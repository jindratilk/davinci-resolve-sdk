# `timeline mark get`

Syntax: `cutagent timeline mark get`

## Search terms

- inspect timeline mark range
- get render range marks
- check video in out points
- check audio in out points
- see timeline range selection
- verify cleared timeline marks

## What it does

Read timeline mark in and out points.

## Do not use when

Do not use this to list colored point markers or marker notes; use the timeline marker-list command for those. Do not use it to discover a timeline's content bounds or duration (`timeline info` / `timeline duration`), because mark ranges may be empty, partial, or outside useful content.

## Preflight and readback

Run it before `timeline mark set` or `timeline mark clear` when the existing range must be preserved or restored. After either mutation, rerun it and compare the relevant category—not merely command success—because the mutation commands do not perform their own mark readback. For a workflow that temporarily changes marks, capture both `video` and `audio` dictionaries and restore them independently.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- A project can have a populated video range and no audio range, different ranges for each, or neither.
- Empty marks are represented as `{}` per category, not `null`, omitted keys, or a shared empty range.

## Examples

- `cutagent timeline mark get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
