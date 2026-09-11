# `clip take select`

Syntax: `cutagent clip take select INDEX [--clip VALUE]`

## Search terms

- switch clip to take 2
- audition another source in take stack
- choose alternate performance
- change active Media Pool source for clip
- restore original take
- toggle between clip takes
- set selected take index

## What it does

Select a take by index.

## Do not use when

Use `clip take add` if the alternative is not yet in the stack, `delete` to remove an alternative, and `finalize` only when the selected source should become permanent and alternatives discarded. Use multicam angle switching for synchronized camera edits over time; a take selection applies one alternate to the whole timeline item.

## Preflight and readback

List the stack and retain each media name/range plus selected index. Inspect/render the full item for source duration, framing, audio, and color differences.

## Public arguments and options

- `INDEX` (required) — Take index
- `--clip` (optional)

## Boundaries and gotchas

- Global `--dry-run` is broken and mutating.
- Dry-run selection of index 2 really selected blue, and the old red selector immediately stopped finding the item.
- Index 3 on a two-take stack returned a detailed out-of-range validation error before calling the selector.
- Switching can cause DaVinci Resolve to normalize take source ranges to the timeline item's length; the blue range changed from 0..23 to 0..22 during the lifecycle.
- The command does not compare fps, resolution, color management, audio channels, or duration before switching.
- Duplicate target names remain first-match and no track/frame selector is available.

## Examples

- `cutagent clip take select --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
