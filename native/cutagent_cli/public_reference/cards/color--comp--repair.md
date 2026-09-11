# `color comp repair`

Syntax: `cutagent color comp repair [--clip VALUE] [--comp VALUE] [--prune-orphans]`

## Search terms

- repair broken Fusion grading comp
- reconnect ColorCorrector graph
- fix disconnected Fusion color tools
- prune orphaned grading tools
- rebuild MediaIn primary MediaOut chain
- canonicalize windows qualifiers trackers
- recover clip-attached color composition

## What it does

Repair a Fusion color composition.

## Do not use when

Use `color comp doctor` or `color graph validate` for read-only diagnosis. Use `color graph normalize` when canonical reconnection is wanted without the repair command's default orphan-pruning contract. Use `color comp flatten` when the explicit goal is to discard all mask helpers and extra primaries.

## Preflight and readback

After repair, run doctor with `--strict`, list tools, export again for a graph diff, render a representative frame, and verify the clip and timeline selection did not change.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index
- `--prune-orphans/--keep-orphans` (optional, default: `true`) — Delete orphaned grading tools

## Boundaries and gotchas

- That can change a previously intentional primary-less MediaIn→MediaOut or ChromaticAdaptation-only graph; doctor may consider those graphs valid without a primary, but repair does not preserve that design.
- Do not rely on global `--dry-run` to preview its exact tool-level changes; use export plus read-only inspection.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color comp repair --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
