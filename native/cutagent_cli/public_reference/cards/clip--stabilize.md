# `clip stabilize`

Syntax: `cutagent clip stabilize [NAME]`

## Search terms

- stabilize shaky clip
- run DaVinci Resolve stabilizer
- smooth handheld footage
- analyze camera shake
- apply clip stabilization
- reduce jitter on shot

## What it does

Run clip stabilization.

## Do not use when

Do not use it when the user specified mode, camera lock, zoom, cropping ratio, smoothing, strength, perspective/translation/similarity, or a re-analyze/reset choice; this command exposes none of them.

## Preflight and readback

Use a uniquely resolved, motion-textured test clip and export baseline frames or a short preview. Wait for analysis completion in the UI, check for error/modal state, compare Viewer/render motion and crop, and inspect the Stabilization panel.

## Public arguments and options

- `NAME` (optional) — Clip name (or current clip)

## Boundaries and gotchas

- The command does not poll analysis progress or block on a completed stabilized render.

## Examples

- `cutagent clip stabilize --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
