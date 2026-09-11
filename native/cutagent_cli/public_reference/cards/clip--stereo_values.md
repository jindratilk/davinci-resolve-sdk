# `clip stereo-values`

Syntax: `cutagent clip stereo-values [CLIP]`

## Search terms

- inspect stereoscopic 3D clip values
- get floating window parameters
- check left eye floating window
- check right eye floating window
- inspect 3D convergence on timeline item
- diagnose stereoscopic clip settings

## What it does

Read stereo 3D values from a timeline item.

## Do not use when

Use `clip source-audio-mapping`, `clip audio-pan`, or Fairlight channel/pan commands for left/right sound. Use timeline/project stereo-3D configuration commands when the whole timeline must be converted or its eye setup changed. Use dedicated stereo setters when convergence or floating windows must be edited; this command is read-only. Do not infer that an empty map means mono audio or that zero-valued video maps prove a properly paired stereoscopic source.

## Preflight and readback

Identify whether the target is a stereoscopic video item and record its timeline/eye configuration.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- The command fails only when none of the three methods is callable.
- Duplicate names and source/display aliases are first-match only.

## Examples

- `cutagent clip stereo-values --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
