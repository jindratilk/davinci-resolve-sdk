# `timeline marker list`

Syntax: `cutagent timeline marker list`

## Search terms

- list timeline markers
- show edit notes on timeline
- find colored timeline flags
- inspect marker names and notes
- get marker frames
- locate review markers
- verify point markers

## What it does

List timeline markers.

## Do not use when

Do not use this to inspect timeline in/out boundaries; use `timeline mark get`. Do not use it for markers attached to source clips or timeline items; use `timeline clip-markers list` or the relevant Media Pool marker command. Do not use marker duration as timeline content duration, and do not use this list to infer that a clip exists under a marker on an empty timeline.

## Preflight and readback

Confirm the intended timeline is active, especially after a targeted marker batch that may have switched timelines. Run the list before marker deletion to capture exact frames, colors, names, and notes. After `timeline marker add`, `batch`, or `delete`, rerun it and compare marker count plus the specific frame and metadata; for batch work, also compare actual frames because collision handling may shift them.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- In agent or lean output, aliases are removed only when values match; normal JSON output retains the full frame/timecode domains.
- Point-marker duration is metadata attached to one marker, not proof of a selected/rendered range.

## Examples

- `cutagent timeline marker list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
