# `render burnin load`

Syntax: `cutagent render burnin load NAME`

## Search terms

- load burn-in preset for render
- activate timecode overlay before export
- use data burn-in on delivery
- apply slate metadata overlay for rendering
- switch render window burn configuration
- load saved burn-in layout
- enable preset before render job

## What it does

Load a burn-in preset for rendering.

## Do not use when

Use `render burnin import` if the preset is only on disk. Do not expect this command to burn pixels by itself; a later render with correct Data Burn-In behavior and visual verification is required.

## Preflight and readback

Record current project/timeline and Data Burn-In configuration, then resolve the exact user preset. After loading, inspect Workspace > Data Burn-In and render a short frame/range through the intended delivery settings. Verify field values for the actual clips because metadata overlays can vary per source even when layout is correct.

## Public arguments and options

- `NAME` (required) — Burn-in preset name

## Boundaries and gotchas

- The command's name says “for rendering,” but it does not attach a preset ID to a particular queued job.

## Examples

- `cutagent render burnin load --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
