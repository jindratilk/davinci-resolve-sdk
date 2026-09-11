# `color comp export`

Syntax: `cutagent color comp export OUTPUT_PATH [--clip VALUE] [--comp VALUE]`

## Search terms

- export Fusion grading comp
- save clip Fusion composition as setting
- back up Fusion color graph
- write .setting from timeline clip
- preserve clip-attached grading tools
- copy Fusion comp to file
- inspect Fusion composition source

## What it does

Export a Fusion color composition.

## Preflight and readback

Record the source clip and one-based composition index alongside the file because the file name carries neither reliably.

## Public arguments and options

- `OUTPUT_PATH` (required) — Output .setting path
- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- The destination must not already exist.
- It does not parse the exported text, compare tool counts, or attempt a round-trip import.

## Examples

- `cutagent color comp export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
