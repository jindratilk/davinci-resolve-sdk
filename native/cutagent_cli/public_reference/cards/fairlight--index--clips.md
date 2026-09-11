# `fairlight index clips`

Syntax: `cutagent fairlight index clips [--track VALUE] [--query VALUE] [--limit VALUE]`

## Search terms

- list Fairlight audio clips
- search timeline audio by name
- inventory dialogue clips
- list clips on audio track
- locate Fairlight clip row
- inspect audio clip start and duration
- search sound effect in timeline
- count matching audio clips
- map clip to Fairlight track
- Fairlight Index clip search

## What it does

List Fairlight Index audio clips for the current timeline.

## Do not use when

Use `fairlight clip linked list` when finding video/audio items linked to one resolved timeline clip, and use media-pool search/list commands for source media not placed in the timeline. For a mutation target, corroborate the returned ID and raw timing with a narrower preflight command rather than selecting solely by a broad substring.

## Preflight and readback

If using `--track`, first inspect `fairlight index tracks` so the 1-based index is unambiguous. Afterward, check `timeline`, echoed `filters`, `count`, `truncated`, track ID/index, and whether raw start/duration values need decoding by the consuming workflow. Because this command is read-only, postconditions concern target identity and freshness, not project mutation.

## Public arguments and options

- `--track/-t` (optional) — Filter by audio track index
- `--query/-q` (optional) — Filter by clip name or DB id
- `--limit` (optional, default: `200`) — Maximum clips to return, 1-1000

## Boundaries and gotchas

- Name matching is substring-based and case-insensitive.
- `--query` does not inspect source filename, media-pool path, track name, clip notes, markers, metadata, or effects.
- It does not merge both layouts.
- Duplicate timeline names in one project can cause rows from multiple matching sequences to be combined.
- It cannot preview counts, IDs, or truncation.

## Examples

- `cutagent fairlight index clips --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
