# `clip reset-node-colors`

Syntax: `cutagent clip reset-node-colors [CLIP]`

## Search terms

- reset Color page node colors
- clear node tile colors
- remove custom color coding from grade nodes
- restore default color node appearance
- reset all node colors on clip
- clear color graph node colors

## What it does

Reset all node colors on a timeline item.

## Do not use when

Use `color node label` to change node labels, Color node delete/reset-grade commands to remove grading operations, `clip color` for the timeline clip's bin/timeline color, and Fusion tools for Fusion node appearance. This command cannot reset only one node or assign a new color. Do not use it as a grade reset: image processing is intentionally preserved.

## Preflight and readback

Inspect the exact clip's Color node graph in the UI and record which nodes have custom display colors; `color nodes` can corroborate count/labels/LUTs but does not expose node display color. Run reset, then visually inspect the Color page node tiles and confirm grade/render output, node count, labels, LUTs, and cache modes remain intact.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- The CLI has no getter for node display colors, so its normal JSON surfaces cannot provide direct before/after proof.
- UI inspection is required.
- Clip-name resolution can be ambiguous with repeated sources.

## Examples

- `cutagent clip reset-node-colors --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
