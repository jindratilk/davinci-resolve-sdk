# `developer capability diff`

Syntax: `cutagent developer capability diff`

## Search terms

- developer capability diff
- Compare feature coverage.
- developer capability diff help
- developer capability diff command

## What it does

Compare feature coverage.

## Do not use when

Use a real file/build/commit comparison for “what changed since version X,” because this command has no before-state.
Do not use this as a compact release gate or documentation/card coverage check.

## Preflight and readback

If historical drift matters, capture and version the prior JSON externally; this command cannot retrieve it.
Fix source/catalog annotations, rebuild if needed, then execute a fresh process and compare captured JSON yourself.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Dry-run performs the same computation and returns the same nested current-state data.

## Examples

- `cutagent developer capability diff --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
