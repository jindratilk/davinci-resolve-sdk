# `color gallery still grab`

Syntax: `cutagent color gallery still grab`

## Search terms

- grab Color page still
- capture current frame and grade
- save shot to gallery
- create gallery reference still
- store current look in still album

## What it does

Grab a still from the current timeline frame.

## Do not use when

Use `timeline grab-still`/frame export when only an image file is needed, `gallery still import` for an existing DRX/image, and `color still grab-all` for one still from every timeline clip. Do not use this when the target album must be explicit: this command has no `--album`, so switch and verify current album first.

## Preflight and readback

Switch to and verify the intended album, place the playhead on the exact representative frame, confirm a video item is under it, and list the album count.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Global `--dry-run` is broken and mutating.

## Examples

- `cutagent color gallery still grab --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
