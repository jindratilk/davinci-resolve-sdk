# `multicam settings`

Syntax: `cutagent multicam settings [--job VALUE] [--job-json VALUE]`

## Search terms

- resolve multicam job defaults
- effective multicam settings
- structured multicam job
- multicam angle order
- multicam default angles
- multicam sync mode
- video source offsets
- multicam timeline defaults

## What it does

Check multicam settings.

## Do not use when

Do not provide both `--job` and `--job-json`. With neither, the command returns guidance rather than an error or resolved settings.
Do not use duplicate sources, duplicate angle labels, a partial/extra angle order, unsupported sync mode, or default angles outside the final order.

## Public arguments and options

- `--job` (optional) — Path to a structured multicam job JSON file
- `--job-json` (optional) — Inline structured multicam job JSON

## Boundaries and gotchas

- Input mode requires exactly one of `--job` or `--job-json`.
- Angles are case-sensitive strings and must be unique.
- Video source offsets must be an object keyed by known angle; signed integer values are accepted.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent multicam settings --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
