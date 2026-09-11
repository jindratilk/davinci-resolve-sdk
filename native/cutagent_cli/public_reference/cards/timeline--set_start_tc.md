# `timeline set-start-tc`

Syntax: `cutagent timeline set-start-tc TIMECODE`

## Search terms

- set timeline start timecode
- change sequence starting TC
- make timeline start at 01:00:00:00
- rebase record timecode
- change timeline hour
- set absolute timeline offset
- restore timeline start TC

## What it does

Set timeline start timecode.

## Do not use when

Do not use it merely to inspect start code; use `timeline start-tc` without a value or `timeline info`. Do not use it to move the cursor (`timeline playhead set`), change source clip timecode/metadata, or offset clips. Do not change start code mid-workflow when downstream ranges/markers/external conform references were authored in the old record domain without deliberately translating them.

## Preflight and readback

Validate the requested frame field is below nominal fps. Restore original start code after temporary testing.

## Public arguments and options

- `TIMECODE` (required) — Start timecode (HH:MM:SS:FF)

## Boundaries and gotchas

- Accepted format is exactly four numeric fields; semicolon is normalized to colon, but minutes/seconds must be ≤59 and frames must be below rounded nominal fps.

## Examples

- `cutagent timeline set-start-tc --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
