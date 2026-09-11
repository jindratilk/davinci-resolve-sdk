# `color comp flatten`

Syntax: `cutagent color comp flatten [--clip VALUE] [--comp VALUE]`

## Search terms

- flatten Fusion grading comp
- remove power windows and qualifiers
- keep only primary ColorCorrector
- strip trackers from Fusion color graph
- simplify clip-attached grade
- delete extra Fusion color primaries
- return grading comp to primary only

## What it does

Flatten a Fusion color composition.

## Preflight and readback

After flatten, run doctor with `--strict`, list/export the remaining graph, and compare a rendered frame against the pre-flatten look; loss of local corrections is the intended risk, not a verification failure by itself.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- The tool was recreated with the same name, making name-only readback look deceptively stable.
- There is no command-specific dry-run branch.
- Do not use global dry-run as the sole safety preview for this destructive operation.
- An out-of-range composition index is rejected before mutation; indices are one-based.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color comp flatten --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
