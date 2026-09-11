# `timeline captions`

Syntax: `cutagent timeline captions`

## Search terms

- choose caption route
- subtitle track or Text+
- captions decision
- caption workflow router
- designed captions choice
- caption clarification
- subtitle export route
- Fusion caption route

## What it does

Chose a caption approach.

## Do not use when

Do not use this command to list, create, edit, import, export, segment, or verify captions. It performs no DaVinci Resolve operation and no local inspection.
Do not choose a route solely from the word “captions” when the user's deliverable, export requirements, typography, and editability remain unclear.

## Preflight and readback

Before execution, recognize that this command is only useful when terminology is ambiguous and a structured routing prompt is desired.
Verify the resulting subtitle items or Fusion overlays with route-specific readback and visual/export evidence.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It does not require a project or timeline.
- It does not inspect subtitle tracks, audio, Text+ items, presets, or templates.
- It does not perform an interactive question; it emits JSON describing a question.
- Normal and `--dry-run` data are identical.

## Examples

- `cutagent timeline captions --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
