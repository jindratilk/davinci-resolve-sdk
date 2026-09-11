# `color graph normalize`

Syntax: `cutagent color graph normalize [--clip VALUE] [--comp VALUE]`

## Search terms

- normalize Fusion grading graph
- reconnect MediaIn ColorCorrector MediaOut
- reorder windows qualifiers trackers
- fix noncanonical Fusion mask chain
- standardize clip-attached color graph
- repair graph without pruning orphans

## What it does

Clean up the grading node graph.

## Do not use when

Use `color graph inspect/validate` for read-only work, `color comp repair` when only previously active helpers should be retained and color orphans may be pruned, and `color comp flatten` when all mask helpers/extra primaries should be removed. Do not normalize an intentionally custom Fusion topology merely to silence validator errors; the canonical layout is specialized for CutAgent color helpers.

## Preflight and readback

Export the composition, inspect/validate it, and review every recognized window/qualifier/tracker—including disconnected ones—because normalize may attach them. Record existing order and custom connections. Afterward inspect plus strict-validate, compare the exported graph, verify tool inputs, and render representative frames.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- The command does not delete them, but survival is not the same as remaining image-active.
- There is no command-specific dry-run branch.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color graph normalize --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
