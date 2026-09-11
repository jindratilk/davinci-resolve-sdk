# `fairlight items`

Syntax: `cutagent fairlight items INDEX`

## Search terms

- list audio clips on track
- show items on A1
- inspect Fairlight track contents
- get audio clip start end
- find gaps on audio track
- list dialogue segments
- inspect clip order on one track
- check whether audio track is empty
- locate audio by record frame
- count clips on A2

## What it does

List audio clips on a track.

## Preflight and readback

Before reading, confirm the active timeline and map the intended 1-based track with `fairlight tracks`.

## Public arguments and options

- `INDEX` (required) — Track index

## Boundaries and gotchas

- Duplicate names are common and remain ambiguous.
- The command does not expose clip selection, source offset, channels, links, gain, pan, fades, plugins, or disabled state.
- Absence must not be interpreted as a default.
- Global dry-run runs before track validation.
- There is no `--limit`; large tracks can produce large arrays.

## Examples

- `cutagent fairlight items --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
