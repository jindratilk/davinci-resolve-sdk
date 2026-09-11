# `media selected set`

Syntax: `cutagent media selected set CLIP`

## Search terms

- highlight asset in bin
- set current Media Pool selection
- choose clip for audio sync
- focus imported media item
- change bin selection by name
- prepare selected source clip

## What it does

Select a media pool clip.

## Do not use when

Do not rely on a duplicate bare name without Media Pool disambiguation.

## Preflight and readback

Search/list and resolve the exact asset, capture current Media Pool selection, then set. Rerun `media selected list` and compare name/type/source path; the setter does not verify selection state. Restore the prior item after temporary workflows if changing the user's GUI focus matters.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name

## Examples

- `cutagent media selected set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
