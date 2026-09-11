# `clip reverse`

Syntax: `cutagent clip reverse [NAME] [--at VALUE]`

## Search terms

- reverse video clip
- play shot backwards
- reverse linked audio video
- make footage run in reverse
- apply backward timemap
- reverse clip without changing duration

## What it does

Reverse linked clips.

## Do not use when

Use `speed-ramp --reverse-incoming` only for one side of a cut-centered ramp.

## Preflight and readback

Inspect current speed/timemap, source and output durations, and export identifiable baseline frames near both source ends. Dry-run by exact record position, then mutate only a disposable Disk project. After reopen, require reverse readback, compare output frame 0/middle/end with the expected reversed source frames, inspect audio polarity/content if audio was included, and ensure item/neighbor positions remain.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--at` (optional) — Record-domain position for deterministic clip selection

## Boundaries and gotchas

- On a 47-frame/24 fps item, the getter inferred only 45 source frames and 95.7447%, not 47/100%.
- `--at` chooses an item; it is not a source offset or reverse pivot.
- Reversed audio must be auditioned separately.
- Dry-run is correctly non-mutating.

## Examples

- `cutagent clip reverse --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
