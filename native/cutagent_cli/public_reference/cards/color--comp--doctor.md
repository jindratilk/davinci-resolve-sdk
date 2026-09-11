# `color comp doctor`

Syntax: `cutagent color comp doctor [--clip VALUE] [--comp VALUE] [--strict]`

## Search terms

- diagnose a Fusion grading comp
- validate clip-attached color tools
- find orphaned Fusion color tools
- check MediaIn MediaOut grading connections
- inspect primary ColorCorrector mask chain
- troubleshoot broken Fusion color composition
- verify windows qualifiers trackers in Fusion

## What it does

Check a Fusion color composition.

## Do not use when

Use `color comp repair` only after this report identifies a graph that should be canonicalized; doctor never reconnects or deletes anything.

## Preflight and readback

Run doctor before any repair/flatten operation and retain the complete errors, warnings, and tool inventory. After a successful mutation, run doctor again without `--strict`, then with `--strict` when zero disconnected grading helpers is a requirement; separately render a representative frame because structural validity does not prove the look.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index
- `--strict` (optional, default: `false`) — Treat orphaned grading tools as errors

## Boundaries and gotchas

- Do not interpret that failure as evidence that the composition is broken.
- `--strict` changes only orphan classification.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color comp doctor --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
