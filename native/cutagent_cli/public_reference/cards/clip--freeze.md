# `clip freeze`

Syntax: `cutagent clip freeze [NAME] [--at VALUE]`

## Search terms

- freeze frame on clip
- hold first frame
- make video still
- stop motion for whole timeline item
- freeze linked audio video
- turn clip into frame hold

## What it does

Freeze linked clips.

## Preflight and readback

Inspect `clip speed` and source/record bounds, export several distinct baseline frames, and ensure the chosen timeline is a disposable Disk project. Dry-run first. After automatic reopen, inspect speed/timemap state and export at least three separated output frames; they should match the intended held source frame, not merely each other.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--at` (optional) — Record-domain position for deterministic clip selection

## Boundaries and gotchas

- Because that bogus source duration becomes the next speed command's input, `clip speed --set 1` would expand this test item toward 120 frames rather than safely restore the original 47-frame state.
- `--at` is only a deterministic item selector.
- The card's identical rendered frames supplied the required DaVinci Resolve reality check.
- Dry-run is correctly non-mutating and speed readback stayed at 100% afterward.

## Examples

- `cutagent clip freeze --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
