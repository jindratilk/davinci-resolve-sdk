# `batch run`

Syntax: `cutagent batch run PATH [--doctor] [--fail-fast]`

## Search terms

- execute CutAgent YAML recipe
- run deterministic batch edit
- apply repeatable edit steps
- execute multi-step DaVinci Resolve recipe
- continue recipe after step failure
- fail fast batch operations
- run recipe with doctor preflight
- automate fixed edit sequence from YAML

## What it does

Apply an edit plan.

## Public arguments and options

- `PATH` (required) — Path to deterministic recipe YAML
- `--doctor` (optional, default: `false`) — Run doctor preflight before steps
- `--fail-fast/--continue-on-error` (optional, default: `true`) — Stop on first step failure

## Boundaries and gotchas

- `--continue-on-error` means continue dispatching, not return success.
- Without `--doctor`, a recipe `doctor` step is just a normal step and obeys fail-fast/continue behavior.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent batch run --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
