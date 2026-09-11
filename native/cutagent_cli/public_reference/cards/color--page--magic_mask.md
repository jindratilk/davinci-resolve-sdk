# `color page magic-mask`

Syntax: `cutagent color page magic-mask [CLIP_NAME] [--direction VALUE] [--regenerate]`

## Search terms

- check Magic Mask support
- can CutAgent use Magic Mask
- Magic Mask availability
- person mask workflow
- object mask workflow
- isolate subject with AI mask
- track subject mask
- regenerate Magic Mask
- foreground matte availability

## What it does

Check Color Page Magic Mask availability.

## Do not use when

Use `color page magic-mask-draw-stroke` when the requested outcome is to create an initial person/object selection, and `color page magic-mask-refine` when adding another explicit refinement stroke to an existing Magic Mask. For geometric Power Windows rather than semantic subject recognition, use the matching `color page power-window-*` command.

## Preflight and readback

After a successful response, translate the intended subject into normalized viewer coordinates and run `magic-mask-draw-stroke`, then inspect that command's screenshot and exported-frame proof.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--direction/--mode` (optional, default: `"bi"`)
- `--regenerate` (optional, default: `false`) — Regenerate an existing Magic Mask

## Boundaries and gotchas

- Despite accepting a clip, direction and `--regenerate`, this command is a pure availability report.
- This command does not test macOS, Accessibility, Screen Recording, a visible DaVinci Resolve window, the Color page, Magic Mask panel visibility, or viewer geometry.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page magic-mask --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
