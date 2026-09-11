# `fairlight item-source patch`

Syntax: `cutagent fairlight item-source patch [--timeline VALUE] [--item-id VALUE] [--track-index VALUE] [--record-frame VALUE] [--record-duration VALUE] [--record-end VALUE] [--source-start-frame VALUE] [--duration-frames VALUE] [--source-end-frame VALUE] [--batch VALUE] [--allow-multiple]`

## Search terms

- patch audio source In and duration
- change Fairlight clip source range
- set audio item source start and length
- use a different part of an audio file
- shorten audio while changing source offset
- set audio source in and out frames
- repair audio timeline item source bounds
- batch patch audio item source offsets
- change waveform content and clip length together
- patch audio clip by track and record frame
- set Fairlight item source end

## What it does

Update audio source timing.

## Do not use when

Use `fairlight clip slip` when the item must keep its current timeline start, end, and duration while only the source content under those fixed boundaries changes.
Use `fairlight clip trim` when the user wants to move one record edge with source-handle, overlap, transition, time-map, and linked-video safeguards.
Do not use `--allow-multiple` to paper over an ambiguous selector. First identify the rows with `fairlight index clips`; enable it only when every same-track/same-start match is deliberately in scope. Prefer exact item IDs for repair work.

## Preflight and readback

Calculate all three resulting values explicitly: source In, duration, and fixed-start record end. Use both `--record-duration` or `--record-end` with a position selector so a stale plan fails instead of hitting a newly edited row.
Finally audition or render the changed phrase.

## Public arguments and options

- `--timeline` (optional) — Target timeline name; defaults to current timeline
- `--item-id` (optional)
- `--track-index` (optional) — Audio track index selector
- `--record-frame` (optional) — Record-domain item start reference
- `--record-duration` (optional) — Optional record-domain item duration check
- `--record-end` (optional) — Optional record-domain item end check
- `--source-start-frame/--source-start` (optional)
- `--duration-frames/--duration` (optional) — Duration to write; defaults to current Duration - source_start
- `--source-end-frame/--source-end` (optional) — Source-domain end frame; writes end-start as Duration
- `--batch/--input` (optional) — Batch JSON path
- `--allow-multiple/--no-allow-multiple` (optional, default: `false`) — Patch all matches when track/start selector is ambiguous

## Boundaries and gotchas

- From a 96-frame item, asking only for source start 48 produces duration 48, not 96.
- `--duration-frames` and `--source-end-frame` are mutually exclusive.
- Source end must be greater than source start; all resulting durations must be positive.
- `--source-start 48f` chooses source frame 48, while `--record-frame 0f` selects the item at timeline-relative record frame zero.
- `--item-id` cannot be combined with track/record selectors.
- Conversely, a track selector is incomplete without `--record-frame`; `--record-duration` and `--record-end` are optional guards, not alternate primary selectors.
- Default behavior rejects that ambiguity with the matching IDs; `--allow-multiple` updates all matches and can alter several overlapping layers at once.
- Explicit `--timeline` leaves the reopened target timeline active.
- Batch input cannot be mixed with any single-patch selector or source option.
- Batch objects recognize only `entries`, `patches`, or `items` as the list container.

## Examples

- `cutagent fairlight item-source patch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
