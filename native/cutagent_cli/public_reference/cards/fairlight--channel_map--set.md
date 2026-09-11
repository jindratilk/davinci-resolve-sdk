# `fairlight channel-map set`

Syntax: `cutagent fairlight channel-map set [--clip VALUE] [--media VALUE] [--mapping-json VALUE]`

## Search terms

- change timeline clip audio channel mapping
- use only left source channel
- use only right source channel
- duplicate one stereo channel to both outputs
- restore normal stereo channel assignment
- fix dialogue recorded on one side
- map channel 1 to stereo clip
- map channel 2 to stereo clip
- change clip attributes audio channels
- set TimelineItem source audio mapping
- route stereo source channel to both sides
- repair one-sided stereo recording

## What it does

Runs the public `fairlight channel-map set` CutAgent command.

## Do not use when

Use `fairlight channel-map clip` to inspect a TimelineItem and `fairlight channel-map media` to inspect a source asset.
Do not use `--media` to change a Media Pool item's Clip Attributes.
Use clip gain/pan commands when the request is about level or stereo position rather than selecting source channels. Use Fairlight track controls when every clip on a mixer track should be affected.

## Preflight and readback

Before mutation, confirm that the active project is a saved, named local Disk project and that the intended timeline is active. List its audio items with names, item IDs, tracks and ranges; prefer the exact item ID when names repeat. Run `fairlight channel-map clip` and retain the complete original mapping.
Afterward, require all three proofs:
If using a single-channel mapping temporarily, restore the retained `[1,2]` mapping when finished and render again. Also recheck selection, playhead and current page if later workflow steps depend on them; only active-timeline restoration is explicit.

## Public arguments and options

- `--clip` (optional) — Timeline clip name or item id
- `--media` (optional) — Media Pool clip name
- `--mapping-json` (optional) — Requested channel mapping JSON

## Boundaries and gotchas

- Active timeline is restored after reopen, but the code does not explicitly restore selected clips, playhead, current page, Fairlight UI state or transient undo history.
- `[1]`, `[2]` and `[1,2]` are the only channel arrays; `[2,1]`, duplicates, empty lists and channel 3+ are rejected.
- `mute` must be the JSON boolean `false`.
- Exact duplicate names in the current timeline are rejected as ambiguous.
- It does not compare rendered audio, loudness, phase, channel content, gain, pan or the rest of the mapping object.
- `--media` is not a second supported route.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight channel-map set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
