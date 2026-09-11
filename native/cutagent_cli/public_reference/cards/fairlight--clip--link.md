# `fairlight clip link`

Syntax: `cutagent fairlight clip link CLIPS...`

## Search terms

- link audio clips on timeline
- group Fairlight clips together
- make audio clips move together
- link dialogue and boom clips
- attach timeline audio items
- create linked clip group
- couple separate audio clips
- link dual-system audio items
- bind multiple timeline clips
- restore clip link relationship
- make edits affect linked audio clips

## What it does

Link two and more Fairlight timeline clips through the DaVinci Resolve.

## Do not use when

Use `fairlight clip unlink` when removing a link relationship.
Use `media sync-audio` or a timeline synchronization workflow when clips need waveform/timecode alignment. Linking preserves their current positions and merely establishes edit linkage.
Use grouping/compound/multicam commands when the user wants a new container or source object.
Do not use this command to link Media Pool items; every argument resolves on the active timeline. Do not use ambiguous filenames or basenames, and do not assume the Fairlight namespace prevents a matching video item from being selected.
Do not add one new member to an existing linked group by supplying only the old member and the newcomer.

## Preflight and readback

Before linking, inventory every intended TimelineItem with unique name, track, absolute range and item ID. Run `fairlight clip linked list` on every prospective member and record all existing partners. Build the full desired group explicitly; if an item already belongs to a group, include every member that must remain linked.
Run `fairlight clip linked list` independently for every intended member and every displaced prior partner. For a group of N distinct items, each item should list the other N−1 items with expected starts/ends. Also verify positions remained unchanged when synchronization was not requested.

## Public arguments and options

- `CLIPS` (required, repeatable) — Audio clip names to link

## Boundaries and gotchas

- Duplicate names are not deduplicated.
- The command's built-in readback checks only the first argument and does not assert that any requested partner appears.
- It can be true for a no-op or invalid duplicate-object group.
- Matching includes source/Media Pool aliases and case-insensitive basenames.
- The first match wins; duplicate/ambiguous occurrences are not rejected and item IDs are not accepted.
- Whitespace-only names are rejected; surrounding whitespace is stripped.
- The command does not require equal starts, ends, durations, tracks or media sources.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight clip link --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
