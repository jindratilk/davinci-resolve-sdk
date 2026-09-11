# `color page magic-mask-draw-stroke`

Syntax: `cutagent color page magic-mask-draw-stroke CLIP_NAME [--mask-type VALUE] --stroke VALUE [--track]`

## Search terms

- draw Magic Mask stroke
- isolate person automatically
- mask a moving subject
- paint subject selection stroke
- AI subject matte
- foreground subject cutout
- create person mask

## What it does

Draw a DaVinci Resolve Color Page Magic Mask stroke.

## Do not use when

Use `color page magic-mask` only to query availability without touching the project, and `color page magic-mask-refine` for an explicit follow-up stroke on an existing selection. Use a `power-window-*` command for a deterministic circle, rectangle, polygon, gradient or curve mask, and qualifier commands for selections driven by hue/saturation/luma. This command also does not expose matte-finesse sliders, alpha-output wiring, compositing, or generic GUI automation.

## Preflight and readback

Keep the DaVinci Resolve window visible on the active Space. Add an alpha output or downstream grade only with the separate command that owns that topology.

## Public arguments and options

- `CLIP_NAME` (required) — Clip name to target on the Color page
- `--mask-type/--mode` (optional, default: `"person"`) — Magic Mask target type: person or object.
- `--stroke` (required) — Normalized frame stroke: x,y;x,y;...
- `--track` (optional, default: `false`) — Run Magic Mask tracking after drawing the stroke

## Boundaries and gotchas

- At least two finite points are required; every x/y must be within 0 through 1.
- The command switches to the Color page but does not restore the previous page.
- The Magic Mask panel must already be open and Accessibility text must include `Magic Mask`; the mode check records whether the title-cased mode label is visible but only absence of the main panel is a hard error.

## Examples

- `cutagent color page magic-mask-draw-stroke --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
