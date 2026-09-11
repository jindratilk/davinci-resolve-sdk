# `media color set`

Syntax: `cutagent media color set NAME COLOR`

## Search terms

- set Media Pool clip color
- color-code source clip
- label footage blue
- assign bin clip color
- mark asset pink
- organize media by clip color
- change source clip display color
- set clip color metadata

## What it does

Set clip color.

## Do not use when

Use `media flag add` when the user means a colored flag; flags can coexist in multiple colors, while clip color is a single replaceable attribute. Use timeline-item color commands when only one timeline occurrence should change rather than the shared Media Pool source. Use color-page grading commands for image color correction—this command affects organizational UI color only.

## Preflight and readback

Dry-run the requested color to see its normalized canonical spelling.

## Public arguments and options

- `NAME` (required) — Clip name
- `COLOR` (required) — Color name (e.g., Blue, Green, Pink)

## Boundaries and gotchas

- It notably does not include Red, Cyan, or the broader flag palette.
- The clip has only one clip color.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent media color set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
