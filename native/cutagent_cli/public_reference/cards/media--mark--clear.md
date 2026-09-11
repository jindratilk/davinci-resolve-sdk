# `media mark clear`

Syntax: `cutagent media mark clear CLIP [--type VALUE]`

## Search terms

- clear Media Pool in out
- reset source clip range
- remove audio source marks
- clear marked portion of media
- remove source selection
- reset source trim points
- clear all clip in out categories
- unmark Media Pool range

## What it does

Clear mark in and out points for a media pool item.

## Do not use when

Use `timeline mark clear` for active timeline boundaries, `media marker delete` for named/color source annotations, and `clip marker delete` for occurrence-owned markers. Do not clear shared Media Pool marks when another pending source-edit workflow depends on them; capture and restore the previous bounds instead.

## Preflight and readback

Run `media mark get` and preserve every returned category. Use an explicit type when only one stream category should be cleared; omit it only when all should be reset. After clearing, rerun get and require the targeted category to be empty while verifying any untargeted categories remain. Restore captured bounds with set if cleanup was temporary.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name
- `--type` (optional, default: `"all"`) — all|video|audio

## Boundaries and gotchas

- Default `--type all` can remove both video and audio source selections from a multi-stream item.

## Examples

- `cutagent media mark clear --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
