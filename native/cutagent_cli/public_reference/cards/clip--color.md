# `clip color`

Syntax: `cutagent clip color [NAME] [--set VALUE] [--clear]`

## Search terms

- set timeline clip color
- color-code an edit clip
- label a clip orange or green
- clear clip color
- organize timeline clips by color
- change occurrence color in DaVinci Resolve
- tag b-roll with a color

## What it does

Check clip color.

## Do not use when

Use `media color set`/`media color clear` when the Media Pool source rather than a particular timeline item is the intended target. Use `clip flag` for one or more colored flags, and clip/media marker commands for a color attached to a particular time. Use Color-page grading commands when the request is to change the rendered picture; this command changes only the editorial label shown in the timeline.

## Preflight and readback

After `--set` or `--clear`, run the getter again and compare the exact returned string. If the color is only temporary workflow state, restore the saved name; clearing is not equivalent to restoring an inherited or previously explicit color.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--set` (optional) — Set color (Orange, Teal, Blue, Green, Pink, etc.)
- `--clear` (optional, default: `false`) — Clear color

## Boundaries and gotchas

- Color matching is case-insensitive at the CLI boundary, but only 24 canonical names are accepted: Apricot, Blue, Brown, Cocoa, Cream, Cyan, Fuchsia, Green, Lavender, Lemon, Lime, Mint, Navy, Olive, Orange, Pink, Purple, Red, Rose, Sand, Sky, Teal, Violet, and Yellow.
- `--set` and `--clear` are mutually exclusive.
- Duplicate names can recolor the wrong occurrence.
- The command does not alter flags.

## Examples

- `cutagent clip color --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
