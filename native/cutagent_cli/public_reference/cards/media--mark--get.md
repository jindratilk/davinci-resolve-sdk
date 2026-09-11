# `media mark get`

Syntax: `cutagent media mark get CLIP`

## Search terms

- inspect source trim marks
- get clip source range
- check audio source in out
- show Media Pool mark points
- verify source selection
- see marked portion of media

## What it does

Check mark in and out points for a media pool item.

## Do not use when

Do not use source marks as proof of a timeline item's current trim; inspect the timeline item because source marks are Media Pool state and the occurrence may use explicit source bounds.

## Preflight and readback

Confirm the exact Media Pool asset and capture its marks before `media mark set` or `clear`. Before an append/edit workflow, decide deliberately whether to honor these marks or supply explicit source frames.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name

## Examples

- `cutagent media mark get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
