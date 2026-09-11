# `clip fusion tool-set`

Syntax: `cutagent clip fusion tool-set TOOL_NAME INPUT_NAME VALUE [--comp VALUE] [--clip VALUE] [--track VALUE] [--record-frame VALUE]`

## Search terms

- set Fusion node input
- change TextPlus StyledText
- edit Fusion parameter from CLI
- set node control value
- change Fusion Inspector input
- modify comp tool property

## What it does

Set a Fusion node value.

## Do not use when

Use a specialized Text+/Fusion workflow when values require points, colors, IDs, expressions, keyframes, or connected modifiers; this CLI surface can supply only one number or string token. Use graph commands for adding/removing/connecting nodes. Use tool-get plus Viewer/render readback after every set, and do not rely on dry-run for safety.

## Preflight and readback

Immediately get the same input, compare type/value, inspect the Viewer at relevant frames, and restore on mismatch.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name
- `INPUT_NAME` (required) — Input name
- `VALUE` (required) — Value to set
- `--comp` (optional, default: `1`)
- `--clip` (optional)
- `--track` (optional) — Video track index selector
- `--record-frame/--at` (optional) — Record-domain frame/time selector

## Boundaries and gotchas

- Global `--dry-run` is broken and mutating.
- There is no frame/time parameter, so this cannot deliberately set or modify an animated keyframe.
- Success does not save the project, prove persistence, or verify rendered output.

## Examples

- `cutagent clip fusion tool-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
