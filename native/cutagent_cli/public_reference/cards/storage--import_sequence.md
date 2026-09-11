# `storage import-sequence`

Syntax: `cutagent storage import-sequence PATTERN [--start-index VALUE] [--end-index VALUE]`

## Search terms

- import image sequence
- numbered DPX sequence
- frame sequence pattern
- image sequence range
- import frames into Media Pool
- percent placeholder sequence

## What it does

Import an image sequence using DaVinci Resolve import options.

## Do not use when

Do not run before confirming the exact active project/current Media Pool bin and DaVinci Resolve's expected sequence-pattern syntax.
Do not trust dry-run to validate pattern existence, matching files, index order, or range contents.
Do not use this for independent still images that should remain separate Media Pool items.
Do not assume one returned item covers every intended frame without inspecting clip properties and missing-frame behavior.

## Preflight and readback

Before execution, enumerate matching files locally, verify zero padding and first/last frame, make the intended Media Pool folder current, and capture existing bin contents.
Use explicit start/end indices when the sequence range must be bounded; verify start is not greater than end yourself because dry-run does not.
Remove accidental imports manually.

## Public arguments and options

- `PATTERN` (required) — Image sequence path/pattern
- `--start-index` (optional) — First sequence index
- `--end-index` (optional) — Last sequence index

## Boundaries and gotchas

- Exact help is `cutagent storage import-sequence PATTERN [--start-index N] [--end-index N]`.
- Dry-run omits start/end indices from its message.
- Dry-run does not validate index ordering.
- CLI integer type parsing still occurs before dry-run.
- It rejects end less than start only when both values are supplied.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent storage import-sequence --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
